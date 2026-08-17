"""Rotas da Central de Chamados (TI) — lógica de dado mora em
`tools/ti/glpi.py` (hoje um mock, ver docstring do módulo), a decisão de
"tem informação suficiente" em `agent/ti/qualidade_chamado.py`; este
módulo só orquestra os dois e cuida do HTTP, mesmo espírito de
`server/ti/seguranca.py` (roda sob demanda, nunca em background)."""

from ollama import AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.ti.qualidade_chamado import avaliar_chamado
from agente_oracle.config import settings
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_ti
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.ti.glpi import Chamado, ClienteGLPIMock

_cliente = ClienteGLPIMock()


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
    }


def registrar(mcp) -> None:
    @mcp.custom_route("/api/ti/chamados", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_ti)
    async def chamados_route(request: Request, usuario: dict) -> Response:
        """Lista os chamados (mock) com o status/avaliação atual."""
        chamados = _cliente.listar()
        return JSONResponse([_chamado_para_json(chamado) for chamado in chamados], headers=CORS_HEADERS)

    @mcp.custom_route("/api/ti/chamados/verificar", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=exigir_modulo_ti)
    async def chamados_verificar_route(request: Request, usuario: dict) -> Response:
        """Roda `avaliar_chamado` em todo chamado ainda `novo` — vago vira
        `aguardando_usuario` com a pergunta da IA; com informação
        suficiente vai direto pra `fila_atendimento`."""
        ollama_client = AsyncClient(host=settings.ollama_host)
        for chamado in _cliente.listar():
            if chamado.status != "novo":
                continue
            avaliacao = await avaliar_chamado(
                ollama_client, settings.ollama_model, chamado.titulo, chamado.descricao, chamado.categoria
            )
            status = "fila_atendimento" if avaliacao.suficiente else "aguardando_usuario"
            mensagem = None if avaliacao.suficiente else avaliacao.mensagem
            _cliente.atualizar_avaliacao(chamado.id, status, mensagem)

        chamados = _cliente.listar()
        return JSONResponse([_chamado_para_json(chamado) for chamado in chamados], headers=CORS_HEADERS)

    @mcp.custom_route("/api/ti/chamados/{id}/reportar", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=exigir_modulo_ti)
    async def chamado_reportar_route(request: Request, usuario: dict) -> Response:
        """Avisa o usuário que o chamado dele está `aguardando_usuario` —
        hoje só marca `reportado_em` (mock, nenhum e-mail sai de verdade
        ainda, ver docstring de `tools/ti/glpi.py`)."""
        try:
            chamado_id = int(request.path_params["id"])
        except ValueError:
            return JSONResponse({"erro": "Chamado não encontrado."}, status_code=404, headers=CORS_HEADERS)

        chamados_por_id = {chamado.id: chamado for chamado in _cliente.listar()}
        if chamado_id not in chamados_por_id:
            return JSONResponse({"erro": "Chamado não encontrado."}, status_code=404, headers=CORS_HEADERS)

        _cliente.reportar_usuario(chamado_id)

        chamado_final = next(chamado for chamado in _cliente.listar() if chamado.id == chamado_id)
        return JSONResponse(_chamado_para_json(chamado_final), headers=CORS_HEADERS)
