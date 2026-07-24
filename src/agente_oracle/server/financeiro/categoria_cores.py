from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.dependencia import exigir_modulo_financeiro
from agente_oracle.server.cors import CORS_HEADERS, resposta_preflight
from agente_oracle.tools.financeiro import categoria_cores as categoria_cores_tools


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/categorias/cores", methods=["GET", "OPTIONS"])
    async def categoria_cores_route(request: Request) -> Response:
        """Lista as cores de categoria personalizadas pelo usuário logado —
        categorias sem registro aqui usam a cor padrão resolvida no frontend."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_modulo_financeiro(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro
        usuario_id = int(usuario_ou_erro["sub"])

        cores = categoria_cores_tools.listar(usuario_id)
        return JSONResponse(cores, headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/categorias/cores/{categoria}", methods=["PUT", "DELETE", "OPTIONS"])
    async def categoria_cor_detalhe_route(request: Request) -> Response:
        """Define (PUT) ou remove (DELETE, volta pra cor padrão) a cor
        personalizada de uma categoria específica do usuário logado."""
        if request.method == "OPTIONS":
            return resposta_preflight("PUT, DELETE, OPTIONS")

        usuario_ou_erro = exigir_modulo_financeiro(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro
        usuario_id = int(usuario_ou_erro["sub"])

        categoria = request.path_params["categoria"]

        if request.method == "PUT":
            corpo = await request.json()
            cor = str(corpo.get("cor") or "").strip()
            if not cor:
                return JSONResponse({"erro": "Informe uma cor."}, status_code=400, headers=CORS_HEADERS)

            resultado = categoria_cores_tools.definir(usuario_id, categoria, cor)
            return JSONResponse(resultado, headers=CORS_HEADERS)

        categoria_cores_tools.remover(usuario_id, categoria)
        return JSONResponse({"ok": True}, headers=CORS_HEADERS)
