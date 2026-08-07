"""Testa a validação de tamanho mínimo de senha (`tools/auth/usuarios.py`,
`senha_fraca`) nas duas rotas que aceitam senha nova: criação de usuário e
troca de senha."""

import uuid

import pytest

pytestmark = pytest.mark.integration


class TestSenhaFracaNaCriacaoDeUsuario:
    def test_senha_curta_e_rejeitada(self, mcp_app, token_dev):
        resposta = mcp_app.post(
            "/api/auth/usuarios",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={
                "usuario": f"teste_{uuid.uuid4().hex[:12]}",
                "senha": "curta12",
                "nome": "Teste Senha Curta",
                "papeis": ["financeiro"],
            },
        )
        assert resposta.status_code == 400
        assert "senha" in resposta.json()["erro"].lower()

    def test_senha_com_tamanho_minimo_e_aceita(self, mcp_app, token_dev):
        login = f"teste_{uuid.uuid4().hex[:12]}"
        resposta = mcp_app.post(
            "/api/auth/usuarios",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={"usuario": login, "senha": "SenhaOk12", "nome": "Teste Senha Ok", "papeis": ["financeiro"]},
        )
        assert resposta.status_code == 201

        mcp_app.delete(f"/api/auth/usuarios/{resposta.json()['id']}", headers={"Authorization": f"Bearer {token_dev}"})


class TestSenhaFracaNaTrocaDeSenha:
    def test_senha_nova_curta_e_rejeitada(self, mcp_app, usuario_teste, token_teste):
        resposta = mcp_app.patch(
            "/api/auth/senha",
            headers={"Authorization": f"Bearer {token_teste}"},
            json={"senha_atual": usuario_teste["senha"], "senha_nova": "curta12"},
        )
        assert resposta.status_code == 400
        assert "senha" in resposta.json()["erro"].lower()
