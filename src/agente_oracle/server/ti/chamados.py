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
filtro de status). `verificar_chamados_aguardando_resposta` é quem cobre
`aguardando_usuario`, mas só reavalia quando detecta uma resposta nova
(Followup mais recente que a última avaliação registrada) — reprocessar
um chamado parado, sem que nada tenha mudado, seria IA gasta à toa; sem
resposta nova, o GLPI já tem o próprio mecanismo de resolver sozinho
depois de 3 dias (`PendingReason` — ver
`tools/ti/glpi.py::ClienteGLPIReal._marcar_aguardando_usuario`).

`processar_chamado_novo` nunca manda a mesma pergunta automática duas
vezes pro mesmo chamado — `ja_foi_avaliado_insuficiente` (calculado por
quem chama, via `tools/ti/uso_ia_chamados.py::ultima_avaliacao`, de
propósito fora desta função testável-com-fake) decide entre perguntar
(primeira vez) e escalar pra um técnico humano (`_escalar_para_tecnico`,
a partir da segunda vez que o MESMO chamado segue insuficiente) — bug
real visto em produção: o mesmo chamado recebendo a mesma pergunta
genérica repetida em dias diferentes, porque ninguém tinha memória do
que já tinha sido perguntado antes.

Amostragem (`tools/ti/amostragem_chamados.py`): só parte dos chamados novos é triada; o botão
"Verificar" de UM chamado ignora a amostra.

`_texto_para_ia` limpa o HTML da descrição antes de mandar pra IA — um
chamado aberto por e-mail pode chegar como um e-mail HTML inteiro
(cabeçalho, rodapé, tabela de estilo), e confirmamos ao vivo que isso
fazia a mesma descrição dar resultado diferente em avaliações
separadas. `chamado.descricao` em si não muda (a tela continua
renderizando o HTML original via `[innerHTML]`).

Regra do GLPI confirmada ao vivo: um chamado SEM NINGUÉM atribuído
(usuário, não só Group) rejeita silenciosamente qualquer troca de
status — o `PATCH` volta 200, mas o status não muda de verdade (era por
isso que o `PendingReason` nunca persistia). `processar_chamado_novo`
atribui a própria conta de serviço da IA (`settings.glpi_conta_ia_id`)
como "segurador de lugar" só no instante da 1ª troca de status, e
desatribui quando a triagem termina (suficiente ou escalado) — a troca
de status já feita continua valendo mesmo depois de desatribuir."""

import asyncio
import logging
import time
from dataclasses import dataclass, replace
from datetime import datetime

from anyio import to_thread
from bs4 import BeautifulSoup
from ollama import AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.ti.qualidade_chamado import avaliar_chamado
from agente_oracle.agent.ti.roteamento_chamado import classificar_categoria
from agente_oracle.config import ollama_model_do_dominio, settings
from agente_oracle.db.connection import DatabaseError
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_desenvolvedor, exigir_modulo_ti
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.ia.cliente_protegido import criar_cliente_protegido
from agente_oracle.tools.ti import amostragem_chamados, categorias, uso_ia_chamados
from agente_oracle.tools.ti import configuracoes as configuracoes_tools
from agente_oracle.tools.ti.glpi import AreaChamado, Chamado, ClienteGLPI, chamado_e_alheio, criar_cliente
from agente_oracle.tools.ti.tecnicos import SemTecnicoNaArea, Tecnico, escolher_tecnico, todos_os_tecnicos

_cliente = criar_cliente(settings)
_logger = logging.getLogger(__name__)

# 5 minutos — equilíbrio entre reagir rápido a chamado novo/atualizado e
# não sobrecarregar a API do GLPI/Ollama com verificação constante.
_INTERVALO_POLLER_SEGUNDOS = 300

# Mesma escolha de `agent/ti/roteamento_chamado.py::_AREA_PADRAO` — duplicada
# de propósito (é 1 linha, não compensa acoplar os dois módulos por isso).
# Só entra em jogo em `_escalar_para_tecnico`, quando o chamado nem tem
# categoria pra derivar a área de outro jeito.
_AREA_PADRAO_ESCALONAMENTO: AreaChamado = "processos"

# Rótulo pra exibição no painel de saúde do roster (`tecnicos_saude_route`,
# só-desenvolvedor) — não existe em nenhum outro lugar do backend hoje,
# área sempre aparece como badge/texto solto no frontend.
_ROTULOS_AREA: dict[AreaChamado, str] = {
    "infra": "Infraestrutura",
    "sistemas": "Sistemas",
    "processos": "Processos",
}


@dataclass(frozen=True)
class ResultadoProcessamento:
    avaliacao_suficiente: bool
    # `None` quando `avaliacao_suficiente` é `False` — o chamado nem chegou
    # a `classificar_categoria`, a pergunta "precisou de embedding" não se
    # aplica. `False` só acontece com `usar_ia=False`.
    precisou_embedding: bool | None


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
        "criado_em": chamado.criado_em.isoformat(),
        "area": chamado.area,
        "tecnico_atribuido": chamado.tecnico_atribuido,
    }


def _ultima_avaliacao_segura(chamado_id: int) -> uso_ia_chamados.RegistroUsoIa | None:
    """Envolve `uso_ia_chamados.ultima_avaliacao` (que de propósito não
    engole erro — ver docstring dela) só nos pontos de chamada: uma falha
    real de Postgres aqui não deveria travar a triagem do chamado em si
    (que não depende de Postgres pra mais nada) — cai no caminho mais
    conservador (trata como primeira vez, pergunta de novo em vez de
    escalar), o mesmo comportamento de antes desta função existir."""
    try:
        return uso_ia_chamados.ultima_avaliacao(chamado_id)
    except DatabaseError:
        _logger.exception("Falha consultando última avaliação do chamado %s", chamado_id)
        return None


def _chamados_da_tela(chamados: list[Chamado], fora_da_amostra: set[int]) -> list[dict]:
    return [
        _chamado_para_json(chamado)
        for chamado in chamados
        if _precisa_atencao(chamado) and chamado.id not in fora_da_amostra
    ]


def _precisa_atencao(chamado: Chamado) -> bool:
    """`fila_atendimento` já tem técnico e área definidos — vira ticket
    normal do GLPI, e a partir daí quem acompanha é o GLPI, não esta tela.
    Só vale mostrar aqui `novo` (ainda não avaliado) e `aguardando_usuario`
    (sem dono, parado esperando o solicitante) — os "perdidos", que é o
    valor real desta auditoria."""
    return chamado.status != "fila_atendimento"


def _saude_por_area(tecnicos: tuple[Tecnico, ...], cargas: dict[str, int]) -> list[dict]:
    """Conta técnico cadastrado por área e monta o roster (nome + carga
    atual no GLPI) de cada uma — extraída de `tecnicos_saude_route` só pra
    ser testável sem precisar montar request/auth/GLPI (mesmo espírito de
    `_chamado_para_json`, `_precisa_atencao` etc. logo abaixo). `cargas` é o
    mesmo dict de `ClienteGLPI.carga_atual_por_tecnico` — técnico sem
    entrada nele (nenhum chamado em `fila_atendimento` no momento) conta
    como 0, não erro."""
    return [
        {
            "area": area,
            "rotulo": rotulo,
            "quantidade": sum(1 for tecnico in tecnicos if tecnico.area == area),
            "tecnicos": [
                {
                    "nome": tecnico.nome,
                    "usuario": tecnico.usuario,
                    "chamados_abertos": cargas.get(tecnico.identificador, 0),
                }
                for tecnico in tecnicos
                if tecnico.area == area
            ],
        }
        for area, rotulo in _ROTULOS_AREA.items()
    ]


def chamado_entra_na_amostra(chamado_id: int, criado_em: datetime | None = None) -> bool:
    """Decide a amostragem; se o banco falhar, não analisa (a próxima rodada tenta de novo)."""
    try:
        return amostragem_chamados.deve_analisar(chamado_id, criado_em)
    except DatabaseError:
        _logger.exception("Falha decidindo a amostragem do chamado %s", chamado_id)
        return False


async def iniciar_poller_verificar_chamados() -> None:
    """Substitui o clique manual em "Verificar Chamados Novos" — roda pra
    sempre em background, a cada `_INTERVALO_POLLER_SEGUNDOS`, enquanto o
    servidor estiver de pé. Única exceção deste projeto à convenção
    "roda sob demanda, nunca em background" (ver `seguranca.py`,
    `auditoria/rotas.py` etc.): sem isso, um chamado novo só seria
    triado quando alguém abrisse a tela e clicasse (ou via webhook, que
    ainda não foi ativado/testado contra a instância real — ver TODO em
    `server/ti/webhook_glpi.py`).

    Duas pernas por rodada, isoladas uma da outra (falha numa não impede a
    outra de rodar): `verificar_chamados_pendentes` cobre chamado `novo`;
    `verificar_chamados_aguardando_resposta` cobre `aguardando_usuario`,
    mas só reavalia quando detecta resposta nova — nunca reprocessa um
    chamado parado sem que nada tenha mudado (gastaria IA à toa; sem
    resposta nova, é o próprio GLPI que resolve sozinho em 3 dias).

    Nunca deixa uma falha de uma rodada (rede instável, Ollama fora do
    ar) derrubar o loop inteiro — loga e tenta de novo na próxima volta.
    Só roda se o GLPI estiver configurado (mesmo espírito de
    `criar_cliente()`: TI opcional não deveria travar nada pros outros
    times); iniciado em `server/app.py::criar_app()`."""
    if not settings.glpi_base_url:
        return
    while True:
        usar_ia = configuracoes_tools.usar_ia_avaliacao_chamado()
        try:
            await verificar_chamados_pendentes(usar_ia)
        except Exception:
            _logger.exception("Falha no poller de verificação de chamados novos")
        try:
            await verificar_chamados_aguardando_resposta(usar_ia)
        except Exception:
            _logger.exception("Falha no poller de verificação de respostas novas")
        await asyncio.sleep(_INTERVALO_POLLER_SEGUNDOS)


async def processar_chamado_novo(
    cliente: ClienteGLPI,
    ollama_client: AsyncClient,
    modelo: str,
    chamado: Chamado,
    cargas: dict[str, int],
    usar_ia: bool,
    ja_foi_avaliado_insuficiente: bool = False,
) -> ResultadoProcessamento:
    """Avalia se o chamado tem informação suficiente. Se não tiver e for
    a primeira vez (`ja_foi_avaliado_insuficiente=False`), marca
    `aguardando_usuario` com a pergunta da IA e para por aqui — igual
    sempre foi. Se **já** tinha sido avaliado insuficiente antes (quem
    chama decide isso, olhando `tools/ti/uso_ia_chamados.py::ultima_avaliacao`
    — de propósito fora desta função, que continua sem tocar Postgres,
    ver abaixo), não manda outra pergunta automática — repetiria algo
    parecido com o que já foi perguntado (bug real visto no #3262: a
    mesma pergunta genérica voltando em dias diferentes). Em vez disso,
    escala pra um técnico humano (`_escalar_para_tecnico`).

    Antes de marcar `aguardando_usuario` pela 1ª vez, atribui a própria
    conta de serviço da IA (`settings.glpi_conta_ia_id`) como "segurador
    de lugar" — confirmado ao vivo contra a instância real que um chamado
    sem NINGUÉM atribuído (usuário, não só Group) rejeita silenciosamente
    qualquer troca de status (o `PATCH` retorna 200, mas o GLPI ignora).
    A conta fica atribuída enquanto o chamado está pendente; quando a
    triagem terminar de verdade (suficiente ou escalado), é desatribuída
    e o técnico de verdade assume — desatribuir não desfaz a troca de
    status já feita (confirmado ao vivo: o status fica onde foi deixado).

    Chamado aberto por e-mail chega do GLPI sem categoria nenhuma
    (`categoria_id is None`) — confirmado com quem cuida do GLPI que
    esse é um padrão real, não uma falha de cadastro. `classificar_categoria`
    já lida bem com "sem categoria atual" (escolhe a melhor categoria
    pelas ~211 reais por similaridade, sem precisar de nada pra
    comparar antes), então esses chamados passam pelo MESMO fluxo de
    quem já tem categoria — a IA escolhe uma do zero, em vez de corrigir
    uma errada. Sem isso, um chamado suficiente e sem categoria ficava
    preso em `novo` pra sempre, sendo reavaliado (e gastando IA) a cada
    rodada do poller sem nunca sair dali — bug real visto em produção.

    Com ou sem categoria de partida, classifica a área, escolhe o técnico de menor carga
    NAQUELE momento (`cargas` é atualizado in-place — importante quando
    processando um lote: duas chamadas seguidas não caem sempre no mesmo
    técnico só porque nenhum dos dois ainda foi salvo no GLPI) — a menos
    que o título/descrição cite um único técnico dessa área pelo nome, que
    aí ganha prioridade sobre a carga (`escolher_tecnico`, ver
    `tools/ti/tecnicos.py`) —, atribui e libera pra fila. Se
    `chamado.tecnico_atribuido` já for exatamente
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
    descricao_limpa = _texto_para_ia(chamado.descricao)
    avaliacao = await avaliar_chamado(
        ollama_client, modelo, chamado.titulo, descricao_limpa, chamado.categoria, usar_ia
    )
    if not avaliacao.suficiente:
        if ja_foi_avaliado_insuficiente:
            await _escalar_para_tecnico(cliente, chamado, cargas)
        else:
            if settings.glpi_conta_ia_id and chamado.tecnico_atribuido != settings.glpi_conta_ia_id:
                await cliente.atribuir_usuario(chamado.id, settings.glpi_conta_ia_id)
            await cliente.atualizar_avaliacao(chamado.id, "aguardando_usuario", avaliacao.mensagem)
        return ResultadoProcessamento(avaliacao_suficiente=False, precisou_embedding=None)

    resultado_classificacao = await classificar_categoria(
        ollama_client,
        settings.ollama_embedding_model,
        chamado.titulo,
        descricao_limpa,
        chamado.categoria_id,
        usar_ia,
    )
    if resultado_classificacao.categoria_id is not None:
        await cliente.atualizar_categoria(chamado.id, resultado_classificacao.categoria_id)

    if settings.glpi_conta_ia_id and chamado.tecnico_atribuido == settings.glpi_conta_ia_id:
        await cliente.desatribuir_usuario(chamado.id, settings.glpi_conta_ia_id)

    tecnico = escolher_tecnico(resultado_classificacao.area, cargas, f"{chamado.titulo}\n{descricao_limpa}")
    if chamado.tecnico_atribuido != tecnico.identificador:
        await cliente.atribuir(chamado.id, resultado_classificacao.area, tecnico.identificador)
    await cliente.atualizar_avaliacao(chamado.id, "fila_atendimento", None)
    cargas[tecnico.identificador] = cargas.get(tecnico.identificador, 0) + 1

    return ResultadoProcessamento(
        avaliacao_suficiente=True, precisou_embedding=resultado_classificacao.precisou_embedding
    )


async def _escalar_para_tecnico(cliente: ClienteGLPI, chamado: Chamado, cargas: dict[str, int]) -> None:
    """Chamado que segue sem informação suficiente numa segunda (ou
    enésima) avaliação não ganha outra pergunta automática — em vez
    disso, atribui um técnico humano de menor carga pra tentar extrair a
    informação diretamente com o solicitante. Atribuir alguém muda o
    status sozinho pra "Em atendimento" (confirmado ao vivo, não dá pra
    atribuir e manter "Pendente") — aceito de propósito: o técnico
    escalado passa a possuir o chamado oficialmente, igual uma resolução
    normal, então o PATCH pra `fila_atendimento` no final é só deixar
    explícito o que o GLPI já fez sozinho.

    Área vem da categoria ATUAL do chamado (`AREA_POR_CATEGORIA_ID`), sem
    chamar `classificar_categoria`/Ollama de novo — mais barato, e nesta
    altura corrigir a categoria não é o problema (falta informação, não
    categoria errada). Cai em `_AREA_PADRAO_ESCALONAMENTO` se o chamado
    não tiver categoria nenhuma (aberto por e-mail)."""
    if settings.glpi_conta_ia_id and chamado.tecnico_atribuido == settings.glpi_conta_ia_id:
        await cliente.desatribuir_usuario(chamado.id, settings.glpi_conta_ia_id)

    area = categorias.AREA_POR_CATEGORIA_ID.get(chamado.categoria_id, _AREA_PADRAO_ESCALONAMENTO)
    tecnico = escolher_tecnico(area, cargas, f"{chamado.titulo}\n{chamado.descricao}")
    if chamado.tecnico_atribuido != tecnico.identificador:
        await cliente.atribuir(chamado.id, area, tecnico.identificador)
    await cliente.atualizar_avaliacao(chamado.id, "fila_atendimento", None)
    cargas[tecnico.identificador] = cargas.get(tecnico.identificador, 0) + 1


def _texto_para_ia(html: str) -> str:
    """GLPI guarda a descrição em HTML — às vezes rich text simples, às
    vezes um e-mail inteiro (cabeçalho, rodapé, tabela de estilo), quando
    o chamado chega por e-mail. Confirmado ao vivo: um chamado real
    chegou com um bloco gigante de HTML de notificação (links "Accept/
    Decline", rodapé "Automaticamente gerado por GLPI", 7 blocos de
    "Acompanhamento" vazios) em volta de uma frase só de conteúdo real —
    e a mesma descrição dava resultado diferente em avaliações separadas
    da IA, provavelmente por causa do volume de marcação sendo
    interpretado junto com o texto. Tira as tags e extrai só o texto —
    não separa boilerplate de conteúdo real (isso exigiria regra própria
    pros padrões de e-mail do GLPI), só corta o ruído da marcação em si.
    Usado só pra montar o texto que vai pra IA — `chamado.descricao` em
    si não muda, a tela continua renderizando o HTML original."""
    sopa = BeautifulSoup(html, "html.parser")
    for tag_indesejada in sopa(["style", "script"]):
        tag_indesejada.decompose()
    return sopa.get_text(separator=" ", strip=True)


def registrar(mcp) -> None:
    @mcp.custom_route("/api/ti/chamados", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_ti)
    async def chamados_route(request: Request, usuario: dict) -> Response:
        """Lista só os chamados que ainda precisam de atenção desta tela —
        ver `_precisa_atencao`. `fila_atendimento` já foi entregue ao GLPI.
        Chamado fora da amostra também não aparece — ver `_chamados_da_tela`."""
        chamados = await _cliente.listar()
        fora_da_amostra = await to_thread.run_sync(amostragem_chamados.ids_fora_da_amostra)
        return JSONResponse(_chamados_da_tela(chamados, fora_da_amostra), headers=CORS_HEADERS)

    @mcp.custom_route("/api/ti/tecnicos", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_ti)
    def tecnicos_route(request: Request, usuario: dict) -> Response:
        """Nomes pro badge "Com {técnico}" na tela de Auditoria — o roster
        de verdade (`tools/ti/tecnicos.py`), aberto pra qualquer um do
        módulo TI. Diferente de `/api/ti/tecnicos-glpi` (candidatos crus
        do GLPI, admin-only, usado só no cadastro de usuário)."""
        return JSONResponse(
            [
                {"identificador": tecnico.identificador, "nome": tecnico.nome}
                for tecnico in todos_os_tecnicos()
            ],
            headers=CORS_HEADERS,
        )

    @mcp.custom_route("/api/ti/tecnicos/saude", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_desenvolvedor)
    async def tecnicos_saude_route(request: Request, usuario: dict) -> Response:
        """Diagnóstico só-desenvolvedor: quantos técnicos existem cadastrados
        por área (e o roster de cada uma, com carga atual no GLPI) — pra
        pegar área com zero técnicos (`escolher_tecnico` levanta
        `SemTecnicoNaArea` nesse caso, ver `tools/ti/tecnicos.py`) antes de
        alguém tropeçar nisso usando a tela de verdade. `todos_os_tecnicos`
        (Postgres, síncrona) roda em thread separada; `carga_atual_por_tecnico`
        (GLPI) continua `await` genuíno."""
        tecnicos = await to_thread.run_sync(todos_os_tecnicos)
        cargas = await _cliente.carga_atual_por_tecnico([tecnico.identificador for tecnico in tecnicos])
        return JSONResponse(_saude_por_area(tecnicos, cargas), headers=CORS_HEADERS)

    @mcp.custom_route("/api/ti/chamados/verificar", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=exigir_modulo_ti)
    async def chamados_verificar_route(request: Request, usuario: dict) -> Response:
        """Dispara manualmente as duas pernas que o poller em background já
        roda sozinho a cada `_INTERVALO_POLLER_SEGUNDOS` — útil pra forçar
        uma rodada na hora, sem esperar o intervalo, durante teste. Ver
        `verificar_chamados_pendentes`/`verificar_chamados_aguardando_resposta`."""
        usar_ia = await to_thread.run_sync(configuracoes_tools.usar_ia_avaliacao_chamado)
        await verificar_chamados_pendentes(usar_ia)
        await verificar_chamados_aguardando_resposta(usar_ia)
        chamados = await _cliente.listar()
        fora_da_amostra = await to_thread.run_sync(amostragem_chamados.ids_fora_da_amostra)
        return JSONResponse(_chamados_da_tela(chamados, fora_da_amostra), headers=CORS_HEADERS)

    @mcp.custom_route("/api/ti/chamados/{id}/verificar", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=exigir_modulo_ti)
    async def chamado_verificar_route(request: Request, usuario: dict) -> Response:
        """Mesma triagem de `chamados_verificar_route`, só que pra 1
        chamado específico — dá suporte a testar manualmente contra o GLPI
        real sem esperar o lote inteiro processar, ou sem depender do
        chamado ainda estar `novo` (ao contrário do lote, roda de novo
        mesmo em `aguardando_usuario`/`fila_atendimento` — útil pra
        reavaliar um chamado depois de ajustar algo manualmente durante
        teste). Também respeita `ja_foi_avaliado_insuficiente`: clicar
        "Verificar" de novo num chamado que já ficou insuficiente antes
        escala pro técnico em vez de gerar outra pergunta repetida.
        Recusa (409) chamado "alheio" (`chamado_e_alheio`) — já
        gerenciado fora do nosso sistema, ver docstring dele."""
        try:
            chamado_id = int(request.path_params["id"])
        except ValueError:
            return JSONResponse({"erro": "Chamado não encontrado."}, status_code=404, headers=CORS_HEADERS)

        chamado = await _cliente.buscar(chamado_id)
        if chamado is None:
            return JSONResponse({"erro": "Chamado não encontrado."}, status_code=404, headers=CORS_HEADERS)

        if chamado_e_alheio(chamado, settings.glpi_conta_ia_id):
            return JSONResponse(
                {"erro": "Chamado gerenciado fora da Auditoria (já tem técnico atribuído no GLPI)."},
                status_code=409,
                headers=CORS_HEADERS,
            )

        ollama_client = criar_cliente_protegido(settings, "ti", sanitizar=True)
        tecnicos = await to_thread.run_sync(todos_os_tecnicos)
        cargas = await _cliente.carga_atual_por_tecnico([tecnico.identificador for tecnico in tecnicos])
        usar_ia = await to_thread.run_sync(configuracoes_tools.usar_ia_avaliacao_chamado)

        registro_anterior = await to_thread.run_sync(_ultima_avaliacao_segura, chamado.id)
        inicio = time.monotonic()
        try:
            resultado = await processar_chamado_novo(
                _cliente,
                ollama_client,
                ollama_model_do_dominio(settings, "ti"),
                chamado,
                cargas,
                usar_ia,
                ja_foi_avaliado_insuficiente=registro_anterior is not None
                and not registro_anterior.avaliacao_suficiente,
            )
        except SemTecnicoNaArea as erro:
            rotulo_area = _ROTULOS_AREA.get(erro.area, erro.area)
            return JSONResponse(
                {
                    "erro": f'Nenhum técnico cadastrado pra área "{rotulo_area}" — cadastre um técnico '
                    "dessa área em Usuários antes de verificar este chamado de novo."
                },
                status_code=422,
                headers=CORS_HEADERS,
            )
        duracao_ms = round((time.monotonic() - inicio) * 1000)
        await to_thread.run_sync(
            uso_ia_chamados.registrar,
            chamado.id,
            resultado.avaliacao_suficiente,
            resultado.precisou_embedding,
            duracao_ms,
        )

        chamado_final = await _cliente.buscar(chamado_id)
        if chamado_final is None:
            return JSONResponse({"erro": "Chamado não encontrado."}, status_code=404, headers=CORS_HEADERS)
        return JSONResponse(_chamado_para_json(chamado_final), headers=CORS_HEADERS)

    @mcp.custom_route("/api/ti/chamados/documentos/{docid}", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_ti)
    async def chamado_documento_route(request: Request, usuario: dict) -> Response:
        """Proxy autenticado pra imagem/anexo real do GLPI — o Angular não
        tem (e não deveria ter) as credenciais da API Legada, então busca o
        arquivo por aqui em vez de apontar `<img src>` direto pro GLPI (que
        além de exigir essa credencial, rejeitaria por CORS)."""
        try:
            docid = int(request.path_params["docid"])
        except ValueError:
            return Response(status_code=404, headers=CORS_HEADERS)

        documento = await _cliente.baixar_documento(docid)
        if documento is None:
            return Response(status_code=404, headers=CORS_HEADERS)
        return Response(documento.conteudo, media_type=documento.content_type, headers=CORS_HEADERS)


async def verificar_chamados_aguardando_resposta(usar_ia: bool) -> None:
    """Segunda perna do poller: chamado `novo` é coberto por
    `verificar_chamados_pendentes`, chamado `aguardando_usuario` é coberto
    aqui — só reavalia quando detecta uma resposta NOVA (Followup mais
    recente que a última avaliação registrada, escrito por alguém que não
    seja a nossa própria conta de serviço), pra não gastar IA (nem uma
    chamada de rede) à toa a cada rodada num chamado que ninguém tocou.

    Sem log de "última avaliação" (`uso_ia_chamados.ultima_avaliacao`), não
    dá pra saber se há resposta nova nem qual o histórico — chamado nessa
    situação é pulado (não deveria acontecer, `aguardando_usuario` só
    existe depois de pelo menos 1 avaliação, mas mais vale pular do que
    assumir errado).

    Reaproveita `processar_chamado_novo` passando uma cópia do chamado com
    a(s) resposta(s) nova(s) anexada(s) à descrição (`dataclasses.replace`)
    — mantém a avaliação da IA olhando o texto completo (pergunta original
    + resposta), sem precisar mudar a assinatura de `avaliar_chamado`.
    Ainda insuficiente escala pro técnico humano (nunca é a "primeira vez"
    aqui, `aguardando_usuario` já implica que já houve 1 avaliação
    insuficiente antes). `todos_os_tecnicos`/`uso_ia_chamados` (Postgres,
    síncronos) rodam em thread separada a cada chamada; o resto do fluxo
    (GLPI/Ollama) continua `await` genuíno."""
    ollama_client = criar_cliente_protegido(settings, "ti", sanitizar=True)
    tecnicos = await to_thread.run_sync(todos_os_tecnicos)
    cargas = await _cliente.carga_atual_por_tecnico([tecnico.identificador for tecnico in tecnicos])

    for chamado in await _cliente.listar():
        if chamado.status != "aguardando_usuario":
            continue
        try:
            registro_anterior = await to_thread.run_sync(_ultima_avaliacao_segura, chamado.id)
            if registro_anterior is None:
                continue
            followups = await _cliente.buscar_followups(chamado.id)
            respostas_novas = [
                followup
                for followup in followups
                if followup.autor_nome != settings.glpi_username
                and followup.criado_em > registro_anterior.criado_em
            ]
            if not respostas_novas:
                continue

            chamado_com_resposta = replace(
                chamado,
                descricao=chamado.descricao
                + "\n\n"
                + "\n".join(followup.conteudo for followup in respostas_novas),
            )
            inicio = time.monotonic()
            resultado = await processar_chamado_novo(
                _cliente,
                ollama_client,
                ollama_model_do_dominio(settings, "ti"),
                chamado_com_resposta,
                cargas,
                usar_ia,
                ja_foi_avaliado_insuficiente=True,
            )
        except Exception:
            _logger.exception("Falha reavaliando resposta nova do chamado %s", chamado.id)
            continue
        duracao_ms = round((time.monotonic() - inicio) * 1000)
        await to_thread.run_sync(
            uso_ia_chamados.registrar,
            chamado.id,
            resultado.avaliacao_suficiente,
            resultado.precisou_embedding,
            duracao_ms,
        )


async def verificar_chamados_pendentes(usar_ia: bool) -> list[Chamado]:
    """Roda `processar_chamado_novo` só em chamado `novo` — `listar()`
    também devolve `aguardando_usuario` (é o que a tela mostra), mas
    reprocessar esses é trabalho de `verificar_chamados_aguardando_resposta`,
    que só reavalia quando detecta resposta nova (ver docstring dela). O
    GLPI também resolve sozinho depois de 3 dias sem resposta
    (`PendingReason`, ver docstring do módulo). `cargas` é buscado uma
    vez só no início do lote — cada chamado processado no meio do loop
    já conta pro próximo, então o lote inteiro se equilibra entre si.

    Mede o tempo de cada chamado e grava em `uso_ia_chamados` — dado
    real de volume/duração pra decidir se a IA nessa etapa está pesando
    (nunca em dinheiro por chamada, Ollama é local — ver docstring de
    `tools/ti/uso_ia_chamados.py`). Chamada tanto pela rota manual
    quanto pelo poller em background (`iniciar_poller_verificar_chamados`).

    Chamado sem avaliação só é processado se entrar na amostra (`chamado_entra_na_amostra`).

    Devolve a listagem completa (`novo` + `aguardando_usuario`, sem
    filtrar por status) — é o que alimenta a tela, mesmo os chamados que
    este loop pulou de propósito.

    Falha isolada num chamado (rede, um erro de validação do GLPI etc.)
    não pode travar o lote inteiro — sem isolar por chamado, um problema
    num único chamado (ex: já visto na prática — GLPI rejeitando
    reatribuir o mesmo técnico) interrompe o `for` no meio, e todo
    chamado que viria depois dele na lista nunca chega a ser processado
    NAQUELE lote nem em nenhum dos seguintes, sempre travando no mesmo
    ponto. `todos_os_tecnicos`/`uso_ia_chamados` (Postgres, síncronos)
    rodam em thread separada a cada chamada; o resto do fluxo (GLPI/
    Ollama) continua `await` genuíno."""
    ollama_client = criar_cliente_protegido(settings, "ti", sanitizar=True)
    tecnicos = await to_thread.run_sync(todos_os_tecnicos)
    cargas = await _cliente.carga_atual_por_tecnico([tecnico.identificador for tecnico in tecnicos])

    for chamado in await _cliente.listar():
        if chamado.status != "novo":
            continue
        inicio = time.monotonic()
        try:
            registro_anterior = await to_thread.run_sync(_ultima_avaliacao_segura, chamado.id)
            if registro_anterior is None and not await to_thread.run_sync(
                chamado_entra_na_amostra, chamado.id, chamado.criado_em
            ):
                continue
            resultado = await processar_chamado_novo(
                _cliente,
                ollama_client,
                ollama_model_do_dominio(settings, "ti"),
                chamado,
                cargas,
                usar_ia,
                ja_foi_avaliado_insuficiente=registro_anterior is not None
                and not registro_anterior.avaliacao_suficiente,
            )
        except Exception:
            _logger.exception("Falha processando o chamado %s", chamado.id)
            continue
        duracao_ms = round((time.monotonic() - inicio) * 1000)
        await to_thread.run_sync(
            uso_ia_chamados.registrar,
            chamado.id,
            resultado.avaliacao_suficiente,
            resultado.precisou_embedding,
            duracao_ms,
        )

    return await _cliente.listar()
