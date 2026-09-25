from anyio import to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_financeiro
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.financeiro import categoria_cores as categoria_cores_tools


def _categoria_cor_detalhe(metodo: str, categoria: str, usuario_id: int, corpo: dict | None) -> Response:
    if metodo == "PUT":
        cor = str((corpo or {}).get("cor") or "").strip()
        if not cor:
            return JSONResponse({"erro": "Informe uma cor."}, status_code=400, headers=CORS_HEADERS)

        resultado = categoria_cores_tools.definir(usuario_id, categoria, cor)
        return JSONResponse(resultado, headers=CORS_HEADERS)

    categoria_cores_tools.remover(usuario_id, categoria)
    return JSONResponse({"ok": True}, headers=CORS_HEADERS)


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/categorias/cores", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
    def categoria_cores_route(request: Request, usuario: dict) -> Response:
        """Lista as cores de categoria personalizadas pelo usuário logado —
        categorias sem registro aqui usam a cor padrão resolvida no frontend."""
        usuario_id = int(usuario["sub"])

        cores = categoria_cores_tools.listar(usuario_id)
        return JSONResponse(cores, headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/categorias/cores/{categoria}", methods=["PUT", "DELETE", "OPTIONS"])
    @rota_protegida("PUT, DELETE, OPTIONS", exigir=exigir_modulo_financeiro)
    async def categoria_cor_detalhe_route(request: Request, usuario: dict) -> Response:
        """Define (PUT) ou remove (DELETE, volta pra cor padrão) a cor
        personalizada de uma categoria específica do usuário logado. Só o
        parsing do corpo (PUT) é assíncrono de verdade; o resto roda em
        thread separada, mesmo padrão de `login_route`."""
        corpo = await request.json() if request.method == "PUT" else None
        return await to_thread.run_sync(
            _categoria_cor_detalhe,
            request.method,
            request.path_params["categoria"],
            int(usuario["sub"]),
            corpo,
        )
