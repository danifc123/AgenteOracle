from anyio import to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_ti
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.ti import configuracoes as configuracoes_tools


def _consultar_usar_ia_avaliacao_chamado() -> Response:
    return JSONResponse(
        {"usar_ia_avaliacao_chamado": configuracoes_tools.usar_ia_avaliacao_chamado()},
        headers=CORS_HEADERS,
    )


def _definir_usar_ia_avaliacao_chamado(corpo: dict) -> Response:
    valor = corpo.get("usar_ia_avaliacao_chamado")
    if not isinstance(valor, bool):
        return JSONResponse(
            {"erro": "Informe usar_ia_avaliacao_chamado como true/false."},
            status_code=400,
            headers=CORS_HEADERS,
        )

    configuracoes_tools.definir_usar_ia_avaliacao_chamado(valor)
    return JSONResponse({"usar_ia_avaliacao_chamado": valor}, headers=CORS_HEADERS)


def registrar(mcp) -> None:
    @mcp.custom_route("/api/ti/configuracoes", methods=["GET", "PUT", "OPTIONS"])
    @rota_protegida("GET, PUT, OPTIONS", exigir=exigir_modulo_ti)
    async def configuracoes_route(request: Request, usuario: dict) -> Response:
        """Hoje só expõe `usar_ia_avaliacao_chamado` — ver
        `tools/ti/configuracoes.py` e a docstring de
        `agent/ti/qualidade_chamado.py::avaliar_chamado`. Só o parsing do
        corpo (PUT) é assíncrono de verdade; o resto roda em thread
        separada, mesmo padrão de `login_route`."""
        if request.method == "GET":
            return await to_thread.run_sync(_consultar_usar_ia_avaliacao_chamado)

        corpo = await request.json()
        return await to_thread.run_sync(_definir_usar_ia_avaliacao_chamado, corpo)
