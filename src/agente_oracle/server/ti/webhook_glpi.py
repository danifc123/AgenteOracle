"""Webhook do GLPI (evento "Ticket created") — dispara a mesma triagem de
`chamados_verificar_route` (`processar_chamado_novo`, em
`server/ti/chamados.py`) assim que um chamado novo é criado, sem esperar o
próximo clique manual em "Verificar". Este projeto não tem fila/job em
background (ver `server/app.py` — tudo roda síncrono dentro do
request/response HTTP), então sem webhook a triagem só acontecia por
polling manual.

Não usa `@rota_protegida`/`exigir_modulo_ti`: essas checagens exigem o JWT
de login do próprio AgenteOracle, que o GLPI não gera — a autenticação
aqui é por segredo compartilhado (`GLPI_WEBHOOK_SECRET`), comparado em
tempo constante (`hmac.compare_digest`) pra não vazar informação por
diferença de tempo de resposta. `_autorizado` sempre rejeita segredo vazio
(não configurado), mesmo sem header nenhum na requisição — sem essa
checagem explícita, `compare_digest("", "")` daria `True` e qualquer
chamada passaria despercebida enquanto `GLPI_WEBHOOK_SECRET` não estivesse
configurada.

`_autorizado` e `processar_webhook` são funções puras/testáveis à parte —
mesmo espírito de `processar_chamado_novo` em `chamados.py` — pra dar pra
testar a lógica sem precisar montar um `Request` do Starlette de verdade;
`glpi_webhook_route` é só o wrapper fino que lê os headers/corpo reais,
mede o tempo, grava o log de uso (`tools/ti/uso_ia_chamados.py` — mesmo
motivo de não fazer isso dentro de `processar_webhook` documentado em
`chamados.py`) e devolve a resposta HTTP.

`processar_webhook` sempre devolve 200 rápido, mesmo se o processamento
interno falhar (loga e não propaga) — evita risco de "retry storm" caso o
GLPI reenvie o evento em caso de erro. Se falhar antes de
`atualizar_avaliacao`, o chamado continua `novo` e
`/api/ti/chamados/verificar` (polling manual) acaba pegando ele depois —
rede de segurança automática, sem esforço extra.

Sem tratamento de CORS/OPTIONS de propósito — o GLPI chama servidor-a-
servidor, nunca por um navegador.

TODO: confirmar contra Setup > Webhooks da instância real —
1) o header exato que o GLPI 11 usa pra mandar o segredo (aqui assumido
   `X-Glpi-Webhook-Secret`);
2) o formato exato do payload do evento "Ticket created" (aqui aceitas
   algumas chaves plausíveis: `items_id`, `id`, `ticket_id` — ver
   `_chamado_id_do_payload`);
3) se o GLPI assina o payload (e como) em vez de/além de mandar só um
   segredo estático no header;
4) se o GLPI faz retry em resposta não-200 (relevante pro "sempre 200"
   acima nunca ter sido validado contra o comportamento real)."""

import hmac
import logging
import time

from ollama import AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.config import settings
from agente_oracle.server.ti.chamados import ResultadoProcessamento, processar_chamado_novo
from agente_oracle.tools.ti import configuracoes as configuracoes_tools
from agente_oracle.tools.ti import uso_ia_chamados
from agente_oracle.tools.ti.glpi import ClienteGLPI, criar_cliente
from agente_oracle.tools.ti.tecnicos import todos_os_tecnicos

# Cliente próprio deste módulo (não importa o `_cliente` privado de
# `chamados.py`) — custa um segundo cache de token/pool HTTP quando
# `ClienteGLPIReal` está em uso, mas evita acoplar dois módulos por uma
# variável de nome com underscore. Ver docstring de `criar_cliente()`.
_cliente = criar_cliente(settings)

_logger = logging.getLogger(__name__)


def _autorizado(segredo_recebido: str, segredo_esperado: str) -> bool:
    """`segredo_esperado` vazio (`GLPI_WEBHOOK_SECRET` não configurado)
    nunca autoriza, mesmo sem nenhum header na requisição — ver docstring
    do módulo pro motivo (`compare_digest("", "")` sozinho daria `True`)."""
    return bool(segredo_esperado) and hmac.compare_digest(segredo_recebido, segredo_esperado)


def _chamado_id_do_payload(corpo: dict) -> int | None:
    """TODO: confirmar o formato exato do payload do evento "Ticket
    created" — aceita algumas chaves plausíveis enquanto isso não é
    confirmado contra a instância real."""
    bruto = corpo.get("items_id", corpo.get("id", corpo.get("ticket_id")))
    try:
        return int(bruto) if bruto is not None else None
    except (TypeError, ValueError):
        return None


async def processar_webhook(
    corpo: dict, cliente: ClienteGLPI, ollama_client: AsyncClient, modelo: str, usar_ia: bool
) -> tuple[int, dict, ResultadoProcessamento | None]:
    """Núcleo do webhook já autenticado (a checagem de segredo mora em
    `glpi_webhook_route`, antes de chamar isto). Devolve
    `(status_code, corpo_json, resultado)` em vez de um `Response` do
    Starlette — `resultado` é `None` nos casos que nem chegaram a
    processar o chamado (400/404); `glpi_webhook_route` usa isso pra saber
    se tem algo a registrar em `uso_ia_chamados`."""
    chamado_id = _chamado_id_do_payload(corpo)
    if chamado_id is None:
        return 400, {"erro": "Payload sem identificador de chamado."}, None

    chamado = await cliente.buscar(chamado_id)
    if chamado is None:
        return 404, {"erro": "Chamado não encontrado."}, None

    resultado = None
    try:
        cargas = await cliente.carga_atual_por_tecnico(
            [tecnico.identificador for tecnico in todos_os_tecnicos()]
        )
        resultado = await processar_chamado_novo(cliente, ollama_client, modelo, chamado, cargas, usar_ia)
    except Exception:
        _logger.exception("Falha processando webhook do GLPI pro chamado %s", chamado_id)

    return 200, {"ok": True}, resultado


def registrar(mcp) -> None:
    @mcp.custom_route("/api/ti/glpi/webhook", methods=["POST"])
    async def glpi_webhook_route(request: Request) -> Response:
        segredo_recebido = request.headers.get("X-Glpi-Webhook-Secret", "")
        if not _autorizado(segredo_recebido, settings.glpi_webhook_secret):
            return JSONResponse({"erro": "Não autorizado."}, status_code=401)

        try:
            corpo = await request.json()
        except Exception:
            return JSONResponse({"erro": "Payload inválido."}, status_code=400)

        ollama_client = AsyncClient(host=settings.ollama_host)
        usar_ia = configuracoes_tools.usar_ia_avaliacao_chamado()
        inicio = time.monotonic()
        status_code, corpo_resposta, resultado = await processar_webhook(
            corpo, _cliente, ollama_client, settings.ollama_model, usar_ia
        )
        if resultado is not None:
            duracao_ms = round((time.monotonic() - inicio) * 1000)
            chamado_id = _chamado_id_do_payload(corpo)
            uso_ia_chamados.registrar(
                chamado_id, resultado.avaliacao_suficiente, resultado.precisou_embedding, duracao_ms
            )
        return JSONResponse(corpo_resposta, status_code=status_code)
