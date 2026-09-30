"""Testa `/api/ia/teto-tokens/{dominio}` de ponta a ponta contra o Postgres
de teste: leitura liberada a quem tem o módulo do domínio, escrita restrita
a quem administra ESSE domínio específico (ou desenvolvedor) — ver
`server/ia/teto_tokens.py`. Isolamento entre domínios (setar o teto do TI
não deveria afetar o do RH) também é coberto aqui."""

import uuid

import pytest

pytestmark = pytest.mark.integration


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _criar_usuario_com_papel(papel: str) -> tuple[str, int]:
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login = f"teste_teto_ia_{uuid.uuid4().hex[:12]}"
    senha = "SenhaDeTeste!123"
    criado = usuarios_tools.criar_usuario(login, senha, f"Teste teto IA ({papel})", [papel])
    return login, criado["id"]


@pytest.fixture
def token_ti_admin(mcp_app):
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login, id_usuario = _criar_usuario_com_papel("ti_admin")
    resposta = mcp_app.post("/api/auth/login", json={"usuario": login, "senha": "SenhaDeTeste!123"})
    assert resposta.status_code == 200
    yield resposta.json()["token"]
    usuarios_tools.deletar_usuario(id_usuario)


@pytest.fixture
def token_rh_admin(mcp_app):
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login, id_usuario = _criar_usuario_com_papel("rh_admin")
    resposta = mcp_app.post("/api/auth/login", json={"usuario": login, "senha": "SenhaDeTeste!123"})
    assert resposta.status_code == 200
    yield resposta.json()["token"]
    usuarios_tools.deletar_usuario(id_usuario)


@pytest.fixture
def token_financeiro_admin(mcp_app):
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login, id_usuario = _criar_usuario_com_papel("financeiro_admin")
    resposta = mcp_app.post("/api/auth/login", json={"usuario": login, "senha": "SenhaDeTeste!123"})
    assert resposta.status_code == 200
    yield resposta.json()["token"]
    usuarios_tools.deletar_usuario(id_usuario)


@pytest.fixture
def token_rh(mcp_app):
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login, id_usuario = _criar_usuario_com_papel("rh")
    resposta = mcp_app.post("/api/auth/login", json={"usuario": login, "senha": "SenhaDeTeste!123"})
    assert resposta.status_code == 200
    yield resposta.json()["token"]
    usuarios_tools.deletar_usuario(id_usuario)


class TestLeitura:
    def test_dominio_invalido_devolve_404(self, mcp_app, token_dev):
        resposta = mcp_app.get("/api/ia/teto-tokens/estoque", headers=_auth(token_dev))
        assert resposta.status_code == 404

    def test_ti_admin_le_o_teto_do_ti(self, mcp_app, token_ti_admin):
        resposta = mcp_app.get("/api/ia/teto-tokens/ti", headers=_auth(token_ti_admin))
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["dominio"] == "ti"
        assert "teto_tokens_diario" in corpo
        assert "tokens_hoje" in corpo

    def test_rh_admin_nao_consegue_ler_o_teto_do_ti(self, mcp_app, token_rh_admin):
        resposta = mcp_app.get("/api/ia/teto-tokens/ti", headers=_auth(token_rh_admin))
        assert resposta.status_code == 403

    def test_sem_token_e_nao_autorizado(self, mcp_app):
        resposta = mcp_app.get("/api/ia/teto-tokens/ti")
        assert resposta.status_code == 401


class TestEscrita:
    def test_desenvolvedor_altera_o_teto_de_qualquer_dominio(self, mcp_app, token_dev):
        resposta = mcp_app.put(
            "/api/ia/teto-tokens/ti", headers=_auth(token_dev), json={"teto_tokens_diario": 12345}
        )
        assert resposta.status_code == 200
        assert resposta.json()["teto_tokens_diario"] == 12345

    def test_ti_admin_altera_o_teto_do_ti(self, mcp_app, token_ti_admin):
        resposta = mcp_app.put(
            "/api/ia/teto-tokens/ti", headers=_auth(token_ti_admin), json={"teto_tokens_diario": 555}
        )
        assert resposta.status_code == 200
        assert resposta.json()["teto_tokens_diario"] == 555

    def test_rh_admin_nao_altera_o_teto_do_ti(self, mcp_app, token_rh_admin):
        resposta = mcp_app.put(
            "/api/ia/teto-tokens/ti", headers=_auth(token_rh_admin), json={"teto_tokens_diario": 1}
        )
        assert resposta.status_code == 403

    def test_financeiro_admin_nao_altera_o_teto_do_rh(self, mcp_app, token_financeiro_admin):
        resposta = mcp_app.put(
            "/api/ia/teto-tokens/rh", headers=_auth(token_financeiro_admin), json={"teto_tokens_diario": 1}
        )
        assert resposta.status_code == 403

    def test_usuario_comum_do_rh_nao_altera_o_teto(self, mcp_app, token_rh):
        resposta = mcp_app.put("/api/ia/teto-tokens/rh", headers=_auth(token_rh), json={"teto_tokens_diario": 1})
        assert resposta.status_code == 403

    def test_valor_invalido_devolve_400(self, mcp_app, token_dev):
        resposta = mcp_app.put("/api/ia/teto-tokens/ti", headers=_auth(token_dev), json={"teto_tokens_diario": -1})
        assert resposta.status_code == 400

    def test_alterar_o_teto_do_ti_nao_afeta_o_teto_do_rh(self, mcp_app, token_dev):
        mcp_app.put("/api/ia/teto-tokens/ti", headers=_auth(token_dev), json={"teto_tokens_diario": 111})
        mcp_app.put("/api/ia/teto-tokens/rh", headers=_auth(token_dev), json={"teto_tokens_diario": 222})

        resposta_ti = mcp_app.get("/api/ia/teto-tokens/ti", headers=_auth(token_dev))
        resposta_rh = mcp_app.get("/api/ia/teto-tokens/rh", headers=_auth(token_dev))

        assert resposta_ti.json()["teto_tokens_diario"] == 111
        assert resposta_rh.json()["teto_tokens_diario"] == 222
