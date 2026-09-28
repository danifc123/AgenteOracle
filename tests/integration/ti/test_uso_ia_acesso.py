"""Testa o acesso de `GET /api/ti/uso-ia` depois de deixar de exigir
`desenvolvedor` — leitura de consumo/custo agora basta ter o módulo TI
liberado (`exigir_modulo_ti`), pedido do usuário, 2026-09-28."""

import uuid

import pytest

pytestmark = pytest.mark.integration

_URL = "/api/ti/uso-ia"


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


class TestUsoIaAcesso:
    def test_time_de_ti_consegue_ver_o_consumo(self, mcp_app, token_ti_admin):
        resposta = mcp_app.get(_URL, headers=_auth(token_ti_admin))
        assert resposta.status_code == 200
        assert "consumo" in resposta.json()

    def test_desenvolvedor_consegue_ver_o_consumo(self, mcp_app, token_dev):
        resposta = mcp_app.get(_URL, headers=_auth(token_dev))
        assert resposta.status_code == 200

    def test_sem_modulo_ti_e_bloqueado(self, mcp_app, token_teste):
        resposta = mcp_app.get(_URL, headers=_auth(token_teste))
        assert resposta.status_code == 403

    def test_sem_token_e_nao_autorizado(self, mcp_app):
        resposta = mcp_app.get(_URL)
        assert resposta.status_code == 401
