"""Decorator que junta os dois passos que TODA `custom_route` protegida
repetia à mão (o preflight de CORS e a checagem de login/autorização via
`exigir_*` de `dependencia.py`) — a função decorada fica só com a lógica de
negócio da rota, recebendo o payload do usuário já resolvido como segundo
argumento.

`func` pode ser `async def` OU uma função comum (`def`): nenhuma query
Oracle/Postgres deste projeto é assíncrona de verdade (o driver `oracledb`
é síncrono — ver `db/connection.py`), então uma rota `async def` que só
faz parsing + query trava o event loop inteiro até a query voltar (um
processo, uma thread — `server/app.py` sobe `uvicorn.run` sem
`workers=`), impedindo QUALQUER outra requisição (inclusive o poller do
GLPI) de avançar nesse meio-tempo. Escrever a rota como `def` comum faz
este decorator rodá-la em thread separada (`anyio.to_thread.run_sync`),
liberando o event loop. Só use `async def` aqui quando a rota realmente
faz I/O assíncrono (ex: `httpx.AsyncClient` contra o GLPI, em
`server/ti/chamados.py`) — nesse caso ela é chamada direto, sem thread.

Rotas que não seguem esse formato (ex: `/api/auth/login`, que não exige
usuário autenticado) continuam escritas na mão, sem este decorator — mas
valem os mesmos dois casos (`async def` só quando há I/O assíncrono de
verdade)."""

import inspect
from collections.abc import Awaitable, Callable
from functools import wraps

from anyio import to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.dependencia import exigir_usuario
from agente_oracle.server.cors import resposta_preflight

_Exigir = Callable[[Request], dict | JSONResponse]
_Handler = Callable[[Request, dict], Awaitable[Response] | Response]


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
        eh_corrotina = inspect.iscoroutinefunction(func)

        @wraps(func)
        async def wrapper(request: Request) -> Response:
            if request.method == "OPTIONS":
                return resposta_preflight(metodos)

            # `exigir` é sempre síncrona (nenhuma variante em dependencia.py/
            # _comum.py::exigir_filiais_liberadas faz I/O assíncrono) e roda
            # ANTES de decidir se a rota em si é thread-offloaded — sem essa
            # thread aqui, toda rota protegida travava o event loop por essa
            # query, convertida ou não.
            usuario_ou_erro = await to_thread.run_sync(exigir, request)
            if isinstance(usuario_ou_erro, JSONResponse):
                return usuario_ou_erro

            if eh_corrotina:
                return await func(request, usuario_ou_erro)
            return await to_thread.run_sync(func, request, usuario_ou_erro)

        return wrapper

    return decorador
