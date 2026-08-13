"""Testa o bloqueio de filial por usuário (`tools/auth/restricoes_filial.py`)
de ponta a ponta: a rota de administração (`GET`/`PUT
/api/auth/usuarios/{id}/filiais-bloqueadas`, restrita ao coordenador do
próprio módulo) e o guard de enforcement usado pelos relatórios do
Financeiro (`server/financeiro/relatorios/_comum.py::
exigir_filiais_liberadas`).

O guard é testado chamando a função diretamente com um `Request` do
Starlette montado à mão, em vez de bater numa rota de relatório de
verdade — os relatórios fixos consultam o schema STAGE, que só existe
contra o Oracle real (ver `test_relatorios_stage.py`), e o que importa
aqui é só o comportamento do guard (nega antes de qualquer query rodar),
não o relatório em si."""

import uuid

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from agente_oracle.server.financeiro.relatorios._comum import exigir_filiais_liberadas
from agente_oracle.tools.auth import restricoes_filial

pytestmark = pytest.mark.integration


def _request_com_filial(token: str, filial: str = "") -> Request:
    query_string = f"filial={filial}".encode() if filial else b""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/x",
        "query_string": query_string,
        "headers": [(b"authorization", f"Bearer {token}".encode())],
    }
    return Request(scope)


@pytest.fixture
def usuario_financeiro_admin():
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login = f"teste_fin_admin_{uuid.uuid4().hex[:12]}"
    senha = "SenhaDeTeste!123"
    criado = usuarios_tools.criar_usuario(
        login, senha, "Coordenador Financeiro (teste)", ["financeiro_admin"]
    )

    yield {"usuario": login, "senha": senha, "id": criado["id"]}

    usuarios_tools.deletar_usuario(criado["id"])


@pytest.fixture
def token_financeiro_admin(mcp_app, usuario_financeiro_admin):
    resposta = mcp_app.post(
        "/api/auth/login",
        json={"usuario": usuario_financeiro_admin["usuario"], "senha": usuario_financeiro_admin["senha"]},
    )
    assert resposta.status_code == 200
    return resposta.json()["token"]


@pytest.fixture
def usuario_rh_admin():
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login = f"teste_rh_admin_{uuid.uuid4().hex[:12]}"
    senha = "SenhaDeTeste!123"
    criado = usuarios_tools.criar_usuario(login, senha, "Coordenador RH (teste)", ["rh_admin"])

    yield {"usuario": login, "senha": senha, "id": criado["id"]}

    usuarios_tools.deletar_usuario(criado["id"])


@pytest.fixture
def token_rh_admin(mcp_app, usuario_rh_admin):
    resposta = mcp_app.post(
        "/api/auth/login", json={"usuario": usuario_rh_admin["usuario"], "senha": usuario_rh_admin["senha"]}
    )
    assert resposta.status_code == 200
    return resposta.json()["token"]


class TestRotaFiliaisBloqueadas:
    def test_admin_do_modulo_bloqueia_e_consulta(self, mcp_app, token_financeiro_admin, usuario_teste):
        resposta = mcp_app.put(
            f"/api/auth/usuarios/{usuario_teste['id']}/filiais-bloqueadas",
            json={"modulo": "financeiro", "filiais": ["0101", "0102"]},
            headers={"Authorization": f"Bearer {token_financeiro_admin}"},
        )
        assert resposta.status_code == 200
        assert resposta.json()["filiais"] == ["0101", "0102"]

        resposta = mcp_app.get(
            f"/api/auth/usuarios/{usuario_teste['id']}/filiais-bloqueadas",
            params={"modulo": "financeiro"},
            headers={"Authorization": f"Bearer {token_financeiro_admin}"},
        )
        assert resposta.status_code == 200
        assert resposta.json()["filiais"] == ["0101", "0102"]

    def test_lista_vazia_desbloqueia_tudo(self, mcp_app, token_financeiro_admin, usuario_teste):
        mcp_app.put(
            f"/api/auth/usuarios/{usuario_teste['id']}/filiais-bloqueadas",
            json={"modulo": "financeiro", "filiais": ["0101"]},
            headers={"Authorization": f"Bearer {token_financeiro_admin}"},
        )

        resposta = mcp_app.put(
            f"/api/auth/usuarios/{usuario_teste['id']}/filiais-bloqueadas",
            json={"modulo": "financeiro", "filiais": []},
            headers={"Authorization": f"Bearer {token_financeiro_admin}"},
        )
        assert resposta.status_code == 200
        assert resposta.json()["filiais"] == []

    def test_admin_de_outro_modulo_e_negado(self, mcp_app, token_rh_admin, usuario_teste):
        resposta = mcp_app.put(
            f"/api/auth/usuarios/{usuario_teste['id']}/filiais-bloqueadas",
            json={"modulo": "financeiro", "filiais": ["0101"]},
            headers={"Authorization": f"Bearer {token_rh_admin}"},
        )
        assert resposta.status_code == 403

    def test_usuario_sem_papel_administrador_e_negado(self, mcp_app, token_teste, usuario_teste):
        resposta = mcp_app.get(
            f"/api/auth/usuarios/{usuario_teste['id']}/filiais-bloqueadas",
            params={"modulo": "financeiro"},
            headers={"Authorization": f"Bearer {token_teste}"},
        )
        assert resposta.status_code == 403

    def test_modulo_desconhecido_e_rejeitado(self, mcp_app, token_financeiro_admin, usuario_teste):
        resposta = mcp_app.put(
            f"/api/auth/usuarios/{usuario_teste['id']}/filiais-bloqueadas",
            json={"modulo": "compras", "filiais": ["0101"]},
            headers={"Authorization": f"Bearer {token_financeiro_admin}"},
        )
        assert resposta.status_code == 403


class TestApagarUsuarioLimpaFiliais:
    def test_deletar_usuario_remove_restricoes(self):
        from agente_oracle.tools.auth import usuarios as usuarios_tools

        login = f"teste_apagar_{uuid.uuid4().hex[:12]}"
        criado = usuarios_tools.criar_usuario(login, "SenhaDeTeste!123", "Apagar (teste)", ["financeiro"])
        restricoes_filial.definir_bloqueadas(criado["id"], "financeiro", ["0101"])
        assert restricoes_filial.filiais_bloqueadas(criado["id"], "financeiro") == {"0101"}

        usuarios_tools.deletar_usuario(criado["id"])

        assert restricoes_filial.filiais_bloqueadas(criado["id"], "financeiro") == set()


class TestGuardExigirFiliaisLiberadas:
    def test_sem_filial_na_query_passa(self, token_teste):
        resultado = exigir_filiais_liberadas(_request_com_filial(token_teste))
        assert isinstance(resultado, dict)

    def test_filial_nao_bloqueada_passa(self, token_teste, usuario_teste):
        restricoes_filial.definir_bloqueadas(usuario_teste["id"], "financeiro", ["0102"])
        resultado = exigir_filiais_liberadas(_request_com_filial(token_teste, "0101"))
        assert isinstance(resultado, dict)

    def test_filial_bloqueada_e_negada(self, token_teste, usuario_teste):
        restricoes_filial.definir_bloqueadas(usuario_teste["id"], "financeiro", ["0101"])
        resultado = exigir_filiais_liberadas(_request_com_filial(token_teste, "0101"))
        assert isinstance(resultado, JSONResponse)
        assert resultado.status_code == 403

    def test_uma_das_filiais_bloqueadas_ja_nega_tudo(self, token_teste, usuario_teste):
        restricoes_filial.definir_bloqueadas(usuario_teste["id"], "financeiro", ["0102"])
        resultado = exigir_filiais_liberadas(_request_com_filial(token_teste, "0101,0102"))
        assert isinstance(resultado, JSONResponse)
        assert resultado.status_code == 403
