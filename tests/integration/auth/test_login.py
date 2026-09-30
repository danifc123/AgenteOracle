"""Testa `/api/auth/login` de ponta a ponta: credenciais reais contra o banco
de teste, incluindo o rate limit temporário em memória (`rate_limit.py`) e o
bloqueio persistente após 3 tentativas erradas (`tools/auth/usuarios.py`),
que só o time de TI (papel `desenvolvedor`) consegue desbloquear. Também
cobre entrar com e-mail em vez de login (`resolver_login`, 2026-09-28)."""

import uuid

import pytest

from agente_oracle.server.auth.rate_limit import LIMITE_TENTATIVAS
from agente_oracle.tools.auth.usuarios import LIMITE_TENTATIVAS_BLOQUEIO

pytestmark = pytest.mark.integration


@pytest.fixture
def usuario_com_email():
    """Mesma ideia de `usuario_teste` (conftest), mas com e-mail cadastrado
    — só assim dá pra testar login por e-mail (`usuario_teste` não tem)."""
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login = f"teste_email_{uuid.uuid4().hex[:12]}"
    senha = "SenhaDeTeste!123"
    email = f"{login}@grupoconceito.com"
    criado = usuarios_tools.criar_usuario(login, senha, "Usuário Com E-mail (integração)", ["financeiro"], email=email)

    yield {"usuario": login, "senha": senha, "id": criado["id"], "email": email}

    usuarios_tools.deletar_usuario(criado["id"])


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
    resposta = mcp_app.post(
        "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": "senha-errada"}
    )
    assert resposta.status_code == 401
    assert "erro" in resposta.json()


def test_login_com_usuario_inexistente(mcp_app):
    resposta = mcp_app.post(
        "/api/auth/login", json={"usuario": "usuario-que-nao-existe-xyz", "senha": "qualquer"}
    )
    assert resposta.status_code == 401


def test_bloqueia_apos_muitas_tentativas_erradas(mcp_app):
    # Usuário inexistente de propósito: isola o teste pro comportamento do
    # rate limit (temporário, em memória) puro, sem cruzar com o bloqueio
    # persistente de conta (que precisa de uma linha real no banco pra
    # travar — ver `test_bloqueia_conta_apos_3_tentativas_erradas` abaixo
    # pra esse outro mecanismo).
    usuario_falso = "rate-limit-teste-xyz"
    for _ in range(LIMITE_TENTATIVAS):
        resposta = mcp_app.post("/api/auth/login", json={"usuario": usuario_falso, "senha": "senha-errada"})
        assert resposta.status_code == 401

    resposta = mcp_app.post("/api/auth/login", json={"usuario": usuario_falso, "senha": "qualquer-coisa"})
    assert resposta.status_code == 429
    corpo = resposta.json()
    assert "segundos_espera" in corpo
    assert corpo["segundos_espera"] > 0
    assert resposta.headers.get("retry-after") is not None


def test_login_bem_sucedido_reseta_o_contador_de_falhas(mcp_app, usuario_teste):
    for _ in range(LIMITE_TENTATIVAS_BLOQUEIO - 1):
        resposta = mcp_app.post(
            "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": "senha-errada"}
        )
        assert resposta.status_code == 401

    resposta = mcp_app.post(
        "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": usuario_teste["senha"]}
    )
    assert resposta.status_code == 200

    # Se o contador não tivesse resetado, essa tentativa (a 1ª desde o
    # sucesso) já contaria como a última antes do bloqueio persistente, em
    # vez de reiniciar a contagem do zero.
    resposta = mcp_app.post(
        "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": "senha-errada"}
    )
    assert resposta.status_code == 401


def test_bloqueia_conta_apos_3_tentativas_erradas(mcp_app, usuario_teste):
    for _ in range(LIMITE_TENTATIVAS_BLOQUEIO - 1):
        resposta = mcp_app.post(
            "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": "senha-errada"}
        )
        assert resposta.status_code == 401

    resposta = mcp_app.post(
        "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": "senha-errada"}
    )
    assert resposta.status_code == 403
    assert "time de TI" in resposta.json()["erro"]


def test_conta_bloqueada_nega_login_mesmo_com_senha_certa(mcp_app, usuario_teste):
    for _ in range(LIMITE_TENTATIVAS_BLOQUEIO):
        mcp_app.post("/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": "senha-errada"})

    resposta = mcp_app.post(
        "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": usuario_teste["senha"]}
    )
    assert resposta.status_code == 403


def test_bloquear_conta_revoga_um_token_ja_emitido(mcp_app, usuario_teste, token_teste):
    """`token_teste` é emitido ANTES do bloqueio abaixo — prova que a conta
    sendo bloqueada corta o acesso na hora, mesmo pra quem já estava logado,
    sem esperar o token expirar sozinho (até `AUTH_TOKEN_HORAS` horas)."""
    for _ in range(LIMITE_TENTATIVAS_BLOQUEIO):
        mcp_app.post("/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": "senha-errada"})

    resposta = mcp_app.patch(
        "/api/auth/perfil",
        headers={"Authorization": f"Bearer {token_teste}"},
        json={"nome": "Nome Novo"},
    )
    assert resposta.status_code == 401


class TestDesbloquearUsuarioRota:
    def test_sem_papel_desenvolvedor_e_negado(self, mcp_app, usuario_teste, token_teste):
        resposta = mcp_app.patch(
            f"/api/auth/usuarios/{usuario_teste['id']}/desbloquear",
            headers={"Authorization": f"Bearer {token_teste}"},
        )
        assert resposta.status_code == 403

    def test_desenvolvedor_desbloqueia_e_conta_volta_a_logar(self, mcp_app, usuario_teste, token_dev):
        for _ in range(LIMITE_TENTATIVAS_BLOQUEIO):
            mcp_app.post(
                "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": "senha-errada"}
            )

        bloqueada = mcp_app.post(
            "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": usuario_teste["senha"]}
        )
        assert bloqueada.status_code == 403

        resposta = mcp_app.patch(
            f"/api/auth/usuarios/{usuario_teste['id']}/desbloquear",
            headers={"Authorization": f"Bearer {token_dev}"},
        )
        assert resposta.status_code == 200

        desbloqueada = mcp_app.post(
            "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": usuario_teste["senha"]}
        )
        assert desbloqueada.status_code == 200

    def test_id_inexistente_retorna_404(self, mcp_app, token_dev):
        resposta = mcp_app.patch(
            "/api/auth/usuarios/999999999/desbloquear",
            headers={"Authorization": f"Bearer {token_dev}"},
        )
        assert resposta.status_code == 404


class TestLoginPorEmail:
    def test_login_com_email_cadastrado(self, mcp_app, usuario_com_email):
        resposta = mcp_app.post(
            "/api/auth/login", json={"usuario": usuario_com_email["email"], "senha": usuario_com_email["senha"]}
        )
        assert resposta.status_code == 200
        # A resposta sempre devolve o LOGIN, não o e-mail digitado — é isso
        # que vira `sub` do token e aparece na sessão do front.
        assert resposta.json()["usuario"] == usuario_com_email["usuario"]

    def test_login_com_email_e_case_insensitive(self, mcp_app, usuario_com_email):
        resposta = mcp_app.post(
            "/api/auth/login",
            json={"usuario": usuario_com_email["email"].upper(), "senha": usuario_com_email["senha"]},
        )
        assert resposta.status_code == 200

    def test_login_continua_funcionando_pelo_login_tambem(self, mcp_app, usuario_com_email):
        resposta = mcp_app.post(
            "/api/auth/login", json={"usuario": usuario_com_email["usuario"], "senha": usuario_com_email["senha"]}
        )
        assert resposta.status_code == 200

    def test_email_com_senha_errada_e_401(self, mcp_app, usuario_com_email):
        resposta = mcp_app.post(
            "/api/auth/login", json={"usuario": usuario_com_email["email"], "senha": "senha-errada"}
        )
        assert resposta.status_code == 401

    def test_email_inexistente_e_401(self, mcp_app):
        resposta = mcp_app.post(
            "/api/auth/login", json={"usuario": "ninguem-com-esse-email@grupoconceito.com", "senha": "qualquer"}
        )
        assert resposta.status_code == 401

    def test_tentativas_erradas_por_login_e_por_email_se_somam_na_mesma_conta(self, mcp_app, usuario_com_email):
        # Prova que `resolver_login` roda ANTES do controle de bloqueio —
        # errar a senha uma vez pelo login e outra pelo e-mail tem que
        # contar pra MESMA conta, não pra dois contadores separados.
        mcp_app.post(
            "/api/auth/login", json={"usuario": usuario_com_email["usuario"], "senha": "senha-errada"}
        )
        mcp_app.post("/api/auth/login", json={"usuario": usuario_com_email["email"], "senha": "senha-errada"})

        resposta = mcp_app.post(
            "/api/auth/login", json={"usuario": usuario_com_email["email"], "senha": "senha-errada"}
        )

        assert resposta.status_code == 403
        assert "time de TI" in resposta.json()["erro"]
