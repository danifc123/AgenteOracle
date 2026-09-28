"""Testa o controle de acesso de `/api/ti/provedores-llm` depois de abrir a
LEITURA (GET) pro time de TI inteiro, mantendo toda ESCRITA restrita a
desenvolvedor (pedido do usuário, 2026-09-28: o time queria acompanhar
consumo/custo sem depender de um desenvolvedor pra cada olhada, mas
cadastrar/editar/ativar/apagar/testar credencial continua sensível
demais pra abrir). Não repete a validação de campo (já coberta pelos
testes unitários de `server/ti/provedores_llm.py`) — só a fronteira de
quem pode fazer o quê."""

import uuid

import pytest

pytestmark = pytest.mark.integration

_URL_LISTA = "/api/ti/provedores-llm"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def token_ti_admin(mcp_app):
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login = f"teste_ti_admin_{uuid.uuid4().hex[:12]}"
    senha = "SenhaDeTeste!123"
    criado = usuarios_tools.criar_usuario(login, senha, "Administrador de TI (teste)", ["ti_admin"])

    resposta = mcp_app.post("/api/auth/login", json={"usuario": login, "senha": senha})
    assert resposta.status_code == 200

    yield resposta.json()["token"]

    usuarios_tools.deletar_usuario(criado["id"])


class TestListarProvedoresLlm:
    def test_time_de_ti_consegue_listar(self, mcp_app, token_ti_admin):
        resposta = mcp_app.get(_URL_LISTA, headers=_auth(token_ti_admin))
        assert resposta.status_code == 200
        assert isinstance(resposta.json(), list)

    def test_desenvolvedor_consegue_listar(self, mcp_app, token_dev):
        resposta = mcp_app.get(_URL_LISTA, headers=_auth(token_dev))
        assert resposta.status_code == 200

    def test_sem_modulo_ti_e_bloqueado(self, mcp_app, token_teste):
        resposta = mcp_app.get(_URL_LISTA, headers=_auth(token_teste))
        assert resposta.status_code == 403

    def test_sem_token_e_nao_autorizado(self, mcp_app):
        resposta = mcp_app.get(_URL_LISTA)
        assert resposta.status_code == 401


class TestCriarProvedorLlm:
    def test_time_de_ti_nao_consegue_cadastrar(self, mcp_app, token_ti_admin):
        resposta = mcp_app.post(
            _URL_LISTA,
            headers=_auth(token_ti_admin),
            json={"nome": "x", "base_url": "http://x", "modelo": "x"},
        )
        assert resposta.status_code == 403

    def test_desenvolvedor_consegue_cadastrar(self, mcp_app, token_dev):
        nome = f"Provedor de teste {uuid.uuid4().hex[:8]}"
        resposta = mcp_app.post(
            _URL_LISTA,
            headers=_auth(token_dev),
            json={"nome": nome, "base_url": "http://127.0.0.1:0", "modelo": "modelo-teste"},
        )
        assert resposta.status_code == 201

        mcp_app.delete(f"{_URL_LISTA}/{resposta.json()['id']}", headers=_auth(token_dev))


class TestEscritaContinuaRestritaADesenvolvedor:
    def test_time_de_ti_nao_consegue_editar(self, mcp_app, token_ti_admin):
        resposta = mcp_app.patch(f"{_URL_LISTA}/1", headers=_auth(token_ti_admin), json={"nome": "x"})
        assert resposta.status_code == 403

    def test_time_de_ti_nao_consegue_apagar(self, mcp_app, token_ti_admin):
        resposta = mcp_app.delete(f"{_URL_LISTA}/1", headers=_auth(token_ti_admin))
        assert resposta.status_code == 403

    def test_time_de_ti_nao_consegue_ativar(self, mcp_app, token_ti_admin):
        resposta = mcp_app.post(f"{_URL_LISTA}/1/ativar", headers=_auth(token_ti_admin))
        assert resposta.status_code == 403

    def test_time_de_ti_nao_consegue_testar_conexao(self, mcp_app, token_ti_admin):
        resposta = mcp_app.post(f"{_URL_LISTA}/1/testar", headers=_auth(token_ti_admin))
        assert resposta.status_code == 403
