"""Testa `rota_protegida` isolado (sem precisar do app real nem de banco):
preflight de CORS, curto-circuito de autorização, e — o que motivou a
mudança — que uma rota escrita como `def` comum roda em thread separada
(via `anyio.to_thread.run_sync`) em vez de travar o event loop, enquanto
uma rota `async def` continua rodando direto nele. Ver docstring de
`server/auth/decorador_rota.py` pro motivo (driver Oracle/Postgres é
síncrono, e o servidor sobe com um único event loop)."""

import threading

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from agente_oracle.server.auth.decorador_rota import rota_protegida


def _permitir(request: Request) -> dict:
    return {"sub": "1", "usuario": "teste"}


def _negar(request: Request) -> JSONResponse:
    return JSONResponse({"erro": "não autorizado"}, status_code=403)


def _app_com_rota(func, exigir=_permitir) -> TestClient:
    rota = Route(
        "/rota-teste",
        rota_protegida("GET, OPTIONS", exigir=exigir)(func),
        methods=["GET", "OPTIONS"],
    )
    return TestClient(Starlette(routes=[rota]))


class TestPreflightEAutorizacao:
    def test_options_devolve_preflight_sem_chamar_o_handler(self):
        chamou = []

        def handler(request, usuario):
            chamou.append(True)
            return JSONResponse({"ok": True})

        resposta = _app_com_rota(handler).options("/rota-teste")

        assert resposta.status_code == 200
        assert chamou == []

    def test_exigir_negando_curto_circuita_antes_do_handler(self):
        chamou = []

        def handler(request, usuario):
            chamou.append(True)
            return JSONResponse({"ok": True})

        resposta = _app_com_rota(handler, exigir=_negar).get("/rota-teste")

        assert resposta.status_code == 403
        assert chamou == []


class TestDispatchSincronoVsAssincrono:
    def test_handler_def_comum_funciona_e_recebe_o_usuario(self):
        def handler(request, usuario):
            return JSONResponse({"usuario": usuario["usuario"]})

        resposta = _app_com_rota(handler).get("/rota-teste")

        assert resposta.status_code == 200
        assert resposta.json() == {"usuario": "teste"}

    def test_handler_async_def_continua_funcionando(self):
        async def handler(request, usuario):
            return JSONResponse({"usuario": usuario["usuario"]})

        resposta = _app_com_rota(handler).get("/rota-teste")

        assert resposta.status_code == 200
        assert resposta.json() == {"usuario": "teste"}

    def test_handler_sincrono_roda_em_thread_diferente_do_assincrono(self):
        # O ponto central da mudança: uma rota `def` (trabalho síncrono, ex:
        # query Oracle/Postgres) não pode rodar na MESMA thread do event
        # loop, senão trava o servidor inteiro até ela voltar — precisa ir
        # pra uma thread separada (anyio.to_thread.run_sync). Uma rota
        # `async def` continua rodando direto no event loop.
        threads: dict[str, int] = {}

        async def handler_async(request, usuario):
            threads["async"] = threading.get_ident()
            return JSONResponse({"ok": True})

        def handler_sync(request, usuario):
            threads["sync"] = threading.get_ident()
            return JSONResponse({"ok": True})

        app = Starlette(
            routes=[
                Route(
                    "/a",
                    rota_protegida("GET, OPTIONS", exigir=_permitir)(handler_async),
                    methods=["GET", "OPTIONS"],
                ),
                Route(
                    "/s",
                    rota_protegida("GET, OPTIONS", exigir=_permitir)(handler_sync),
                    methods=["GET", "OPTIONS"],
                ),
            ]
        )
        cliente = TestClient(app)

        assert cliente.get("/a").status_code == 200
        assert cliente.get("/s").status_code == 200
        assert threads["sync"] != threads["async"]
