"""Rotas da Auditoria de Chamados (TI) — lógica de dado mora em
`tools/ti/glpi.py` (integração real com o GLPI, sem cliente mock — ver
`criar_cliente()`), a decisão de "tem informação
suficiente" em `agent/ti/qualidade_chamado.py`, a validação/correção de
categoria (e a área que vem dela) em `agent/ti/roteamento_chamado.py`, e a
escolha de técnico por menor carga em `tools/ti/tecnicos.py`; este módulo
só orquestra os quatro e cuida do HTTP.

`processar_chamado_novo` é a função reutilizável entre `/verificar`
(rota manual, usada hoje só pra testar 1 chamado por vez),
`iniciar_poller_verificar_chamados` (roda sozinho em background, a cada
`_INTERVALO_POLLER_SEGUNDOS` — ver docstring dele pro motivo de este
módulo abrir uma exceção à convenção "nunca em background" do resto do
projeto) e o webhook do GLPI (`server/ti/webhook_glpi.py`, disparado no
evento "Ticket created") — os três fazem exatamente a mesma triagem, só
o gatilho muda. Ela em si nunca toca o Postgres de log de uso
(`tools/ti/uso_ia_chamados.py`) — só devolve `ResultadoProcessamento` pra
quem chamou decidir o que fazer com isso; `verificar_chamados_pendentes`
é quem mede o tempo e grava o log, de propósito (mantém
`processar_chamado_novo` testável com fakes, sem precisar de Postgres
real pra rodar teste unitário — ver docstring de `uso_ia_chamados.py`).

`verificar_chamados_pendentes` só reprocessa chamado `novo` — a TELA
continua mostrando `aguardando_usuario` também (`chamados_route`, sem
filtro de status), mas reavaliar de novo um chamado que já está esperando
resposta do solicitante, a cada 5 minutos, sem que nada tenha mudado, é
uma chamada de IA gasta à toa; o GLPI já tem o próprio mecanismo de
resolver sozinho depois de 3 dias sem resposta (`PendingReason` — ver
`tools/ti/glpi.py::ClienteGLPIReal._marcar_aguardando_usuario`). Um
chamado assim só é reavaliado de novo via o botão "Verificar" individual
por chamado (`/api/ti/chamados/{id}/verificar`, que não tem esse filtro
de propósito — é o suporte a teste manual)."""

import asyncio
import logging
import time
from dataclasses import dataclass

from ollama import AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.ti.qualidade_chamado import avaliar_chamado
from agente_oracle.agent.ti.roteamento_chamado import classificar_categoria
from agente_oracle.config import settings
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_ti
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.ti import configuracoes as configuracoes_tools
from agente_oracle.tools.ti import uso_ia_chamados
from agente_oracle.tools.ti.glpi import Chamado, ClienteGLPI, criar_cliente
from agente_oracle.tools.ti.tecnicos import TECNICOS, escolher_tecnico

_cliente = criar_cliente(settings)
_logger = logging.getLogger(__name__)

# 5 minutos — equilíbrio entre reagir rápido a chamado novo/atualizado e
# não sobrecarregar a API do GLPI/Ollama com verificação constante.
_INTERVALO_POLLER_SEGUNDOS = 300


@dataclass(frozen=True)
class ResultadoProcessamento:
    avaliacao_suficiente: bool
    # `None` quando `avaliacao_suficiente` é `False` — o chamado nem chegou
    # a `classificar_categoria`, a pergunta "precisou de embedding" não se
    # aplica. `False` cobre dois casos: `usar_ia=False`, ou chamado sem
    # categoria (nunca chega a chamar `classificar_categoria`, que é quem
    # de fato usaria embedding).
    precisou_embedding: bool | None


def _precisa_atencao(chamado: Chamado) -> bool:
    """`fila_atendimento` já tem técnico e área definidos — vira ticket
    normal do GLPI, e a partir daí quem acompanha é o GLPI, não esta tela.
    Só vale mostrar aqui `novo` (ainda não avaliado) e `aguardando_usuario`
    (sem dono, parado esperando o solicitante) — os "perdidos", que é o
    valor real desta auditoria."""
    return chamado.status != "fila_atendimento"


def _chamado_para_json(chamado: Chamado) -> dict:
    return {
        "id": chamado.id,
        "titulo": chamado.titulo,
        "descricao": chamado.descricao,
        "categoria": chamado.categoria,
        "status": chamado.status,
        "solicitante": chamado.solicitante,
        "email": chamado.email,
        "avaliacao_mensagem": chamado.avaliacao_mensagem,
        "reportado_em": chamado.reportado_em.isoformat() if chamado.reportado_em else None,
        "criado_em": chamado.criado_em.isoformat(),
        "area": chamado.area,
        "tecnico_atribuido": chamado.tecnico_atribuido,
    }


async def processar_chamado_novo(
    cliente: ClienteGLPI,
    ollama_client: AsyncClient,
    modelo: str,
    chamado: Chamado,
    cargas: dict[str, int],
    usar_ia: bool,
) -> ResultadoProcessamento:
    """Avalia se o chamado tem informação suficiente; se não tiver, marca
    `aguardando_usuario` com a pergunta da IA e para por aqui.

    Sem categoria (`categoria_id is None`) — chamado aberto por e-mail,
    confirmado com o responsável do GLPI que esses já entram direto na
    fila de TI sem categoria — a auditoria também para por aqui: não tem
    categoria pra corrigir nem base pra decidir área/técnico, então só a
    checagem de informação suficiente se aplica. De propósito, nada é
    escrito no GLPI quando o conteúdo já está suficiente (marcar
    `fila_atendimento` sem ninguém de fato atribuído deixaria o status
    real do GLPI, "Em atendimento (atribuído)", mentindo) — o chamado
    continua aparecendo nesta tela até um humano decidir o que fazer com
    ele; só o caso insuficiente escreve algo (o pedido de mais
    informação, igual o fluxo normal).

    Com categoria, classifica a área, escolhe o técnico de menor carga
    NAQUELE momento (`cargas` é atualizado in-place — importante quando
    processando um lote: duas chamadas seguidas não caem sempre no mesmo
    técnico só porque nenhum dos dois ainda foi salvo no GLPI), atribui e
    libera pra fila. Se `chamado.tecnico_atribuido` já for exatamente
    esse técnico, pula a atribuição — confirmado contra a instância
    real que o GLPI rejeita (`400 ERROR_INVALID_PARAMETER`) atribuir a
    MESMA pessoa com o mesmo papel duas vezes. Isso acontece quando um
    chamado ficou "meio processado" numa rodada anterior (técnico
    atribuído, mas a chamada seguinte — marcar `fila_atendimento` —
    falhou ou foi interrompida antes de terminar); sem esse pulo, o
    chamado ficaria travado pra sempre, tropeçando nessa mesma falha a
    cada rodada do poller.

    `usar_ia` vem de `tools/ti/configuracoes.py` (lido pela rota, nunca
    aqui — ver docstring de `uso_ia_chamados.py` pro motivo de manter
    Postgres fora das funções testáveis com fake)."""
    avaliacao = await avaliar_chamado(
        ollama_client, modelo, chamado.titulo, chamado.descricao, chamado.categoria, usar_ia
    )
    if not avaliacao.suficiente:
        await cliente.atualizar_avaliacao(chamado.id, "aguardando_usuario", avaliacao.mensagem)
        return ResultadoProcessamento(avaliacao_suficiente=False, precisou_embedding=None)

    if chamado.categoria_id is None:
        return ResultadoProcessamento(avaliacao_suficiente=True, precisou_embedding=False)

    resultado_classificacao = await classificar_categoria(
        ollama_client,
        settings.ollama_embedding_model,
        chamado.titulo,
        chamado.descricao,
        chamado.categoria_id,
        usar_ia,
    )
    if resultado_classificacao.categoria_id is not None:
        await cliente.atualizar_categoria(chamado.id, resultado_classificacao.categoria_id)

    tecnico = escolher_tecnico(resultado_classificacao.area, cargas)
    if chamado.tecnico_atribuido != tecnico.identificador:
        await cliente.atribuir(chamado.id, resultado_classificacao.area, tecnico.identificador)
    await cliente.atualizar_avaliacao(chamado.id, "fila_atendimento", None)
    cargas[tecnico.identificador] = cargas.get(tecnico.identificador, 0) + 1

    return ResultadoProcessamento(
        avaliacao_suficiente=True, precisou_embedding=resultado_classificacao.precisou_embedding
    )


async def verificar_chamados_pendentes(usar_ia: bool) -> list[Chamado]:
    """Roda `processar_chamado_novo` só em chamado `novo` — `listar()`
    também devolve `aguardando_usuario` (é o que a tela mostra), mas
    reavaliar de novo um chamado que já está esperando resposta do
    solicitante, sem que nada tenha mudado, é uma chamada de IA gasta à
    toa a cada rodada; o GLPI já resolve sozinho depois de 3 dias sem
    resposta (`PendingReason`, ver docstring do módulo). `cargas` é
    buscado uma vez só no início do lote — cada chamado processado no
    meio do loop já conta pro próximo, então o lote inteiro se
    equilibra entre si.

    Mede o tempo de cada chamado e grava em `uso_ia_chamados` — dado
    real de volume/duração pra decidir se a IA nessa etapa está pesando
    (nunca em dinheiro por chamada, Ollama é local — ver docstring de
    `tools/ti/uso_ia_chamados.py`). Chamada tanto pela rota manual
    quanto pelo poller em background (`iniciar_poller_verificar_chamados`).

    Devolve a listagem completa (`novo` + `aguardando_usuario`, sem
    filtrar por status) — é o que alimenta a tela, mesmo os chamados que
    este loop pulou de propósito."""
    ollama_client = AsyncClient(host=settings.ollama_host)
    cargas = await _cliente.carga_atual_por_tecnico([tecnico.identificador for tecnico in TECNICOS])

    for chamado in await _cliente.listar():
        if chamado.status != "novo":
            continue
        inicio = time.monotonic()
        resultado = await processar_chamado_novo(
            _cliente, ollama_client, settings.ollama_model, chamado, cargas, usar_ia
        )
        duracao_ms = round((time.monotonic() - inicio) * 1000)
        uso_ia_chamados.registrar(
            chamado.id, resultado.avaliacao_suficiente, resultado.precisou_embedding, duracao_ms
        )

    return await _cliente.listar()


async def iniciar_poller_verificar_chamados() -> None:
    """Substitui o clique manual em "Verificar Chamados Novos" — roda pra
    sempre em background, a cada `_INTERVALO_POLLER_SEGUNDOS`, enquanto o
    servidor estiver de pé. Única exceção deste projeto à convenção
    "roda sob demanda, nunca em background" (ver `seguranca.py`,
    `auditoria/rotas.py` etc.): sem isso, um chamado novo só seria
    triado quando alguém abrisse a tela e clicasse (ou via webhook, que
    ainda não foi ativado/testado contra a instância real — ver TODO em
    `server/ti/webhook_glpi.py`).

    Só reprocessa `novo` (ver `verificar_chamados_pendentes`) — não
    reavalia `aguardando_usuario` de novo a cada rodada, de propósito
    (gastaria IA à toa; esse caso é o botão "Verificar" individual ou o
    próprio GLPI resolvendo sozinho em 3 dias).

    Nunca deixa uma falha de uma rodada (rede instável, Ollama fora do
    ar) derrubar o loop inteiro — loga e tenta de novo na próxima volta.
    Só roda se o GLPI estiver configurado (mesmo espírito de
    `criar_cliente()`: TI opcional não deveria travar nada pros outros
    times); iniciado em `server/app.py::criar_app()`."""
    if not settings.glpi_base_url:
        return
    while True:
        try:
            usar_ia = configuracoes_tools.usar_ia_avaliacao_chamado()
            await verificar_chamados_pendentes(usar_ia)
        except Exception:
            _logger.exception("Falha no poller de verificação de chamados")
        await asyncio.sleep(_INTERVALO_POLLER_SEGUNDOS)


def registrar(mcp) -> None:
    @mcp.custom_route("/api/ti/chamados/{id}/reportar", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=exigir_modulo_ti)
    async def chamado_reportar_route(request: Request, usuario: dict) -> Response:
        """Avisa o usuário que o chamado dele está `aguardando_usuario` —
        `ClienteGLPIReal.reportar_usuario` é no-op de propósito nesta fase,
        nenhum e-mail sai de verdade ainda, ver docstring de
        `tools/ti/glpi.py`."""
        try:
            chamado_id = int(request.path_params["id"])
        except ValueError:
            return JSONResponse({"erro": "Chamado não encontrado."}, status_code=404, headers=CORS_HEADERS)

        chamado = await _cliente.buscar(chamado_id)
        if chamado is None:
            return JSONResponse({"erro": "Chamado não encontrado."}, status_code=404, headers=CORS_HEADERS)

        await _cliente.reportar_usuario(chamado_id)

        chamado_final = await _cliente.buscar(chamado_id)
        return JSONResponse(_chamado_para_json(chamado_final), headers=CORS_HEADERS)

    @mcp.custom_route("/api/ti/chamados", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_ti)
    async def chamados_route(request: Request, usuario: dict) -> Response:
        """Lista só os chamados que ainda precisam de atenção desta tela —
        ver `_precisa_atencao`. `fila_atendimento` já foi entregue ao GLPI."""
        chamados = await _cliente.listar()
        return JSONResponse(
            [_chamado_para_json(chamado) for chamado in chamados if _precisa_atencao(chamado)],
            headers=CORS_HEADERS,
        )

    @mcp.custom_route("/api/ti/chamados/verificar", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=exigir_modulo_ti)
    async def chamados_verificar_route(request: Request, usuario: dict) -> Response:
        """Dispara manualmente a mesma verificação que o poller em
        background já roda sozinho a cada `_INTERVALO_POLLER_SEGUNDOS` —
        útil pra forçar uma rodada na hora, sem esperar o intervalo,
        durante teste. Ver `verificar_chamados_pendentes`."""
        usar_ia = configuracoes_tools.usar_ia_avaliacao_chamado()
        chamados = await verificar_chamados_pendentes(usar_ia)
        return JSONResponse(
            [_chamado_para_json(chamado) for chamado in chamados if _precisa_atencao(chamado)],
            headers=CORS_HEADERS,
        )

    @mcp.custom_route("/api/ti/chamados/{id}/verificar", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=exigir_modulo_ti)
    async def chamado_verificar_route(request: Request, usuario: dict) -> Response:
        """Mesma triagem de `chamados_verificar_route`, só que pra 1
        chamado específico — dá suporte a testar manualmente contra o GLPI
        real sem esperar o lote inteiro processar, ou sem depender do
        chamado ainda estar `novo` (ao contrário do lote, roda de novo
        mesmo em `aguardando_usuario`/`fila_atendimento` — útil pra
        reavaliar um chamado depois de ajustar algo manualmente durante
        teste)."""
        try:
            chamado_id = int(request.path_params["id"])
        except ValueError:
            return JSONResponse({"erro": "Chamado não encontrado."}, status_code=404, headers=CORS_HEADERS)

        chamado = await _cliente.buscar(chamado_id)
        if chamado is None:
            return JSONResponse({"erro": "Chamado não encontrado."}, status_code=404, headers=CORS_HEADERS)

        ollama_client = AsyncClient(host=settings.ollama_host)
        cargas = await _cliente.carga_atual_por_tecnico([tecnico.identificador for tecnico in TECNICOS])
        usar_ia = configuracoes_tools.usar_ia_avaliacao_chamado()

        inicio = time.monotonic()
        resultado = await processar_chamado_novo(
            _cliente, ollama_client, settings.ollama_model, chamado, cargas, usar_ia
        )
        duracao_ms = round((time.monotonic() - inicio) * 1000)
        uso_ia_chamados.registrar(
            chamado.id, resultado.avaliacao_suficiente, resultado.precisou_embedding, duracao_ms
        )

        chamado_final = await _cliente.buscar(chamado_id)
        if chamado_final is None:
            return JSONResponse({"erro": "Chamado não encontrado."}, status_code=404, headers=CORS_HEADERS)
        return JSONResponse(_chamado_para_json(chamado_final), headers=CORS_HEADERS)
