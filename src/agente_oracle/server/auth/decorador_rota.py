"""Decorator que junta os dois passos que TODA `custom_route` protegida
repetia à mão (o preflight de CORS e a checagem de login/autorização via
`exigir_*` de `dependencia.py`) — a função decorada fica só com a lógica de
negócio da rota, recebendo o payload do usuário já resolvido como segundo
argumento.

Rotas que não seguem esse formato (ex: `/api/auth/login`, que não exige
usuário autenticado) continuam escritas na mão, sem este decorator."""

from collections.abc import Awaitable, Callable
from functools import wraps

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.dependencia import exigir_usuario
from agente_oracle.server.cors import resposta_preflight

_Exigir = Callable[[Request], dict | JSONResponse]
_Handler = Callable[[Request, dict], Awaitable[Response]]


def rota_protegida(
    metodos: str, exigir: _Exigir = exigir_usuario
) -> Callable[[_Handler], Callable[[Request], Awaitable[Response]]]:
    """`metodos` é a mesma string já passada pra `resposta_preflight` (ex:
    "GET, OPTIONS") — igual ao que vai no `methods=[...]` do
    `@mcp.custom_route` logo acima na pilha de decorators. `exigir` é uma das
    funções de `dependencia.py` (`exigir_usuario` por padrão, ou uma variante
    como `exigir_administrador`/`exigir_desenvolvedor`/`exigir_modulo_financeiro`
    pra exigir mais que só estar logado)."""

    def decorador(func: _Handler) -> Callable[[Request], Awaitable[Response]]:
        @wraps(func)
        async def wrapper(request: Request) -> Response:
            if request.method == "OPTIONS":
                return resposta_preflight(metodos)

            usuario_ou_erro = exigir(request)
            if isinstance(usuario_ou_erro, JSONResponse):
                return usuario_ou_erro

            return await func(request, usuario_ou_erro)

        return wrapper

    return decorador
