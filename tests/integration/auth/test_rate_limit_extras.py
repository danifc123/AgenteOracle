"""Testa o rate limit (`server/auth/rate_limit.py`) reaproveitado em duas
rotas além do login: troca de senha (chave `"senha:"`) e criação de usuário
(chave `"criar_usuario:"`) — namespaces separadas, então não compartilham
contador nem com o rate limit do login nem entre si."""

import uuid

import pytest

from agente_oracle.server.auth.rate_limit import LIMITE_TENTATIVAS

pytestmark = pytest.mark.integration


def test_troca_de_senha_bloqueia_apos_muitas_tentativas_com_senha_atual_errada(
    mcp_app, usuario_teste, token_teste
):
    for _ in range(LIMITE_TENTATIVAS):
        resposta = mcp_app.patch(
            "/api/auth/senha",
            headers={"Authorization": f"Bearer {token_teste}"},
            json={"senha_atual": "senha-atual-errada", "senha_nova": "SenhaNova123"},
        )
        assert resposta.status_code == 400

    # A tentativa seguinte é bloqueada mesmo com a senha atual CERTA.
    resposta = mcp_app.patch(
        "/api/auth/senha",
        headers={"Authorization": f"Bearer {token_teste}"},
        json={"senha_atual": usuario_teste["senha"], "senha_nova": "SenhaNova123"},
    )
    assert resposta.status_code == 429
    assert resposta.headers.get("retry-after") is not None


def test_troca_de_senha_bem_sucedida_reseta_o_contador(mcp_app, usuario_teste, token_teste):
    for _ in range(LIMITE_TENTATIVAS - 1):
        mcp_app.patch(
            "/api/auth/senha",
            headers={"Authorization": f"Bearer {token_teste}"},
            json={"senha_atual": "senha-atual-errada", "senha_nova": "SenhaNova123"},
        )

    resposta = mcp_app.patch(
        "/api/auth/senha",
        headers={"Authorization": f"Bearer {token_teste}"},
        json={"senha_atual": usuario_teste["senha"], "senha_nova": "SenhaNova123Nova"},
    )
    assert resposta.status_code == 200

    resposta = mcp_app.patch(
        "/api/auth/senha",
        headers={"Authorization": f"Bearer {token_teste}"},
        json={"senha_atual": "outra-senha-errada", "senha_nova": "SenhaNova123"},
    )
    assert resposta.status_code == 400  # não 429 — o sucesso reiniciou a contagem


def test_criacao_de_usuario_bloqueia_apos_muitas_contas_seguidas(mcp_app, token_dev):
    ids_criados = []
    try:
        for _ in range(LIMITE_TENTATIVAS):
            resposta = mcp_app.post(
                "/api/auth/usuarios",
                headers={"Authorization": f"Bearer {token_dev}"},
                json={
                    "usuario": f"teste_rl_{uuid.uuid4().hex[:12]}",
                    "senha": "SenhaOk12345",
                    "nome": "Teste Rate Limit",
                    "papeis": ["financeiro"],
                },
            )
            assert resposta.status_code == 201
            ids_criados.append(resposta.json()["id"])

        resposta = mcp_app.post(
            "/api/auth/usuarios",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={
                "usuario": f"teste_rl_{uuid.uuid4().hex[:12]}",
                "senha": "SenhaOk12345",
                "nome": "Teste Rate Limit",
                "papeis": ["financeiro"],
            },
        )
        assert resposta.status_code == 429
    finally:
        for id_criado in ids_criados:
            mcp_app.delete(
                f"/api/auth/usuarios/{id_criado}", headers={"Authorization": f"Bearer {token_dev}"}
            )
