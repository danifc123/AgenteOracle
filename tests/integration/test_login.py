"""Testa `/api/auth/login` de ponta a ponta: credenciais reais contra o banco
de teste, incluindo o rate limit adicionado nesta sessão (bloqueio por
usuário após tentativas erradas seguidas, com reset no sucesso)."""

import pytest

from agente_oracle.server.auth.rate_limit import LIMITE_TENTATIVAS

pytestmark = pytest.mark.integration


def test_login_com_credenciais_validas(mcp_app, usuario_teste):
    resposta = mcp_app.post(
        "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": usuario_teste["senha"]}
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["usuario"] == usuario_teste["usuario"]
    assert "token" in corpo
    assert corpo["papeis"] == ["financeiro"]


def test_login_com_senha_errada(mcp_app, usuario_teste):
    resposta = mcp_app.post("/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": "senha-errada"})
    assert resposta.status_code == 401
    assert "erro" in resposta.json()


def test_login_com_usuario_inexistente(mcp_app):
    resposta = mcp_app.post("/api/auth/login", json={"usuario": "usuario-que-nao-existe-xyz", "senha": "qualquer"})
    assert resposta.status_code == 401


def test_bloqueia_apos_muitas_tentativas_erradas(mcp_app, usuario_teste):
    for _ in range(LIMITE_TENTATIVAS):
        resposta = mcp_app.post(
            "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": "senha-errada"}
        )
        assert resposta.status_code == 401

    # A tentativa seguinte é bloqueada mesmo com a senha CERTA — o bloqueio é
    # por usuário, não valida a senha antes de checar o limite.
    resposta = mcp_app.post(
        "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": usuario_teste["senha"]}
    )
    assert resposta.status_code == 429
    corpo = resposta.json()
    assert "segundos_espera" in corpo
    assert corpo["segundos_espera"] > 0
    assert resposta.headers.get("retry-after") is not None


def test_login_bem_sucedido_reseta_o_contador_de_falhas(mcp_app, usuario_teste):
    for _ in range(LIMITE_TENTATIVAS - 1):
        resposta = mcp_app.post(
            "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": "senha-errada"}
        )
        assert resposta.status_code == 401

    resposta = mcp_app.post(
        "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": usuario_teste["senha"]}
    )
    assert resposta.status_code == 200

    # Se o contador não tivesse resetado, essa tentativa cairia direto no
    # bloqueio (429) por já estar no limite antes do login bem-sucedido.
    resposta = mcp_app.post(
        "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": "senha-errada"}
    )
    assert resposta.status_code == 401
