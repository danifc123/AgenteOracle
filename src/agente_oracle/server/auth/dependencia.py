"""Checagem de login pras rotas HTTP protegidas — cada `custom_route` que
precisa de usuário logado chama `exigir_usuario(request)` no início e, se o
retorno for um `JSONResponse` (401), devolve isso direto em vez de continuar."""

from starlette.requests import Request
from starlette.responses import JSONResponse

from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.auth.token import verificar_token


def exigir_usuario(request: Request) -> dict | JSONResponse:
    cabecalho = request.headers.get("authorization", "")
    if not cabecalho.startswith("Bearer "):
        return JSONResponse({"erro": "Não autenticado."}, status_code=401, headers=CORS_HEADERS)

    payload = verificar_token(cabecalho.removeprefix("Bearer "))
    if payload is None:
        return JSONResponse({"erro": "Sessão expirada ou inválida."}, status_code=401, headers=CORS_HEADERS)

    return payload
