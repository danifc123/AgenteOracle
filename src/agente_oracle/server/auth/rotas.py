from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.cors import CORS_HEADERS, resposta_preflight
from agente_oracle.tools.auth.token import gerar_token
from agente_oracle.tools.auth.usuarios import autenticar


def registrar(mcp) -> None:
    @mcp.custom_route("/api/auth/login", methods=["POST", "OPTIONS"])
    async def login_route(request: Request) -> Response:
        """Endpoint HTTP usado pela tela de login do frontend."""
        if request.method == "OPTIONS":
            return resposta_preflight()

        corpo = await request.json()
        usuario = str(corpo.get("usuario", "")).strip()
        senha = str(corpo.get("senha", ""))

        dados = autenticar(usuario, senha) if usuario and senha else None
        if dados is None:
            return JSONResponse({"erro": "Usuário ou senha inválidos."}, status_code=401, headers=CORS_HEADERS)

        token = gerar_token(dados["id"], dados["usuario"], dados["nome"], dados["papeis"])
        return JSONResponse(
            {"token": token, "usuario": dados["usuario"], "nome": dados["nome"], "papeis": dados["papeis"]},
            headers=CORS_HEADERS,
        )
