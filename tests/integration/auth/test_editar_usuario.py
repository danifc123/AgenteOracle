"""Testa `PATCH /api/auth/usuarios/{id}` — editar dados de um usuário já
cadastrado (nome, papéis, senha opcional, vínculo com técnico do GLPI).
Mesma validação de papel/GLPI do cadastro (POST), reaproveitada via
`_validar_papeis_e_glpi` — aqui cobre só o que é específico da EDIÇÃO
(usuário precisa existir, login não muda, senha é opcional); a cobertura
completa da validação de GLPI já está em `test_usuarios_tecnico_glpi.py`."""

import uuid

import pytest

pytestmark = pytest.mark.integration

_EMAIL_TECNICO_FAKE = "tecnico.teste@grupoconceito.com"


class _ClienteGlpiFake:
    def __init__(self, area, email: str | None = _EMAIL_TECNICO_FAKE):
        self._area = area
        self._email = email

    async def buscar_area_do_tecnico(self, usuario_id):
        return self._area

    async def buscar_email_do_tecnico(self, usuario_id):
        return self._email


@pytest.fixture
def usuario_com_email():
    """Segunda conta, já com e-mail cadastrado — usada só pra testar que
    `atualizar_usuario` rejeita tentar colocar esse MESMO e-mail em outra
    conta (`EmailJaUsado`)."""
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login = f"teste_email_dup_{uuid.uuid4().hex[:12]}"
    criado = usuarios_tools.criar_usuario(
        login, "SenhaDeTeste!123", "Já Com E-mail", ["financeiro"], email=f"{login}@grupoconceito.com"
    )

    yield criado

    usuarios_tools.deletar_usuario(criado["id"])


@pytest.fixture
def usuario_criado(mcp_app, token_dev):
    login = f"teste_editar_{uuid.uuid4().hex[:12]}"
    resposta = mcp_app.post(
        "/api/auth/usuarios",
        headers={"Authorization": f"Bearer {token_dev}"},
        json={
            "usuario": login,
            "senha": "SenhaOk123",
            "nome": "Antes de Editar",
            "papeis": ["financeiro"],
        },
    )
    assert resposta.status_code == 201
    corpo = resposta.json()

    yield corpo

    mcp_app.delete(f"/api/auth/usuarios/{corpo['id']}", headers={"Authorization": f"Bearer {token_dev}"})


class TestEditarUsuario:
    def test_edita_nome_e_papeis(self, mcp_app, token_dev, usuario_criado):
        resposta = mcp_app.patch(
            f"/api/auth/usuarios/{usuario_criado['id']}",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={"nome": "Depois de Editar", "papeis": ["financeiro_admin"]},
        )

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["nome"] == "Depois de Editar"
        assert corpo["papeis"] == ["financeiro_admin"]
        assert corpo["usuario"] == usuario_criado["usuario"]  # login não muda

    def test_login_continua_o_mesmo_mesmo_se_mandado_no_corpo(self, mcp_app, token_dev, usuario_criado):
        resposta = mcp_app.patch(
            f"/api/auth/usuarios/{usuario_criado['id']}",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={"usuario": "tentativa-de-trocar-login", "nome": "Nome Novo", "papeis": ["financeiro"]},
        )

        assert resposta.status_code == 200
        assert resposta.json()["usuario"] == usuario_criado["usuario"]

    def test_sem_senha_no_corpo_mantem_a_senha_atual(self, mcp_app, token_dev, usuario_criado):
        resposta = mcp_app.patch(
            f"/api/auth/usuarios/{usuario_criado['id']}",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={"nome": "Nome Novo", "papeis": ["financeiro"]},
        )
        assert resposta.status_code == 200

        login_ainda_funciona = mcp_app.post(
            "/api/auth/login", json={"usuario": usuario_criado["usuario"], "senha": "SenhaOk123"}
        )
        assert login_ainda_funciona.status_code == 200

    def test_com_senha_nova_troca_a_senha(self, mcp_app, token_dev, usuario_criado):
        resposta = mcp_app.patch(
            f"/api/auth/usuarios/{usuario_criado['id']}",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={"nome": "Nome Novo", "papeis": ["financeiro"], "senha": "SenhaNovaOk123"},
        )
        assert resposta.status_code == 200

        login_com_senha_antiga = mcp_app.post(
            "/api/auth/login", json={"usuario": usuario_criado["usuario"], "senha": "SenhaOk123"}
        )
        assert login_com_senha_antiga.status_code == 401

        login_com_senha_nova = mcp_app.post(
            "/api/auth/login", json={"usuario": usuario_criado["usuario"], "senha": "SenhaNovaOk123"}
        )
        assert login_com_senha_nova.status_code == 200

    def test_senha_fraca_e_rejeitada(self, mcp_app, token_dev, usuario_criado):
        resposta = mcp_app.patch(
            f"/api/auth/usuarios/{usuario_criado['id']}",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={"nome": "Nome Novo", "papeis": ["financeiro"], "senha": "123"},
        )
        assert resposta.status_code == 400

    def test_usuario_inexistente_e_404(self, mcp_app, token_dev):
        resposta = mcp_app.patch(
            "/api/auth/usuarios/999999999",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={"nome": "Nome Novo", "papeis": ["financeiro"]},
        )
        assert resposta.status_code == 404

    def test_sem_nome_ou_papel_e_rejeitado(self, mcp_app, token_dev, usuario_criado):
        resposta = mcp_app.patch(
            f"/api/auth/usuarios/{usuario_criado['id']}",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={"nome": "", "papeis": []},
        )
        assert resposta.status_code == 400

    def test_sem_token_e_nao_autorizado(self, mcp_app, usuario_criado):
        resposta = mcp_app.patch(
            f"/api/auth/usuarios/{usuario_criado['id']}", json={"nome": "X", "papeis": ["financeiro"]}
        )
        assert resposta.status_code == 401

    def test_papel_sem_permissao_de_quem_edita_e_rejeitado(self, mcp_app, token_dev, usuario_criado):
        # Mesma regra do cadastro: só quem já tem um papel de acesso total
        # (ex: `desenvolvedor`) pode atribuir outro papel de acesso total —
        # aqui confirmado no caminho de EDIÇÃO, não só criação.
        login_admin_comum = f"teste_admin_comum_{uuid.uuid4().hex[:12]}"
        criado = mcp_app.post(
            "/api/auth/usuarios",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={
                "usuario": login_admin_comum,
                "senha": "SenhaOk123",
                "nome": "Admin Comum",
                "papeis": ["financeiro_admin"],
            },
        )
        assert criado.status_code == 201
        token_admin_comum = mcp_app.post(
            "/api/auth/login", json={"usuario": login_admin_comum, "senha": "SenhaOk123"}
        ).json()["token"]

        resposta = mcp_app.patch(
            f"/api/auth/usuarios/{usuario_criado['id']}",
            headers={"Authorization": f"Bearer {token_admin_comum}"},
            json={"nome": "Nome Novo", "papeis": ["desenvolvedor"]},
        )
        assert resposta.status_code == 403

        mcp_app.delete(f"/api/auth/usuarios/{criado.json()['id']}", headers={"Authorization": f"Bearer {token_dev}"})

    def test_vincula_tecnico_glpi_reaproveitando_a_mesma_validacao(self, mcp_app, token_dev, usuario_criado, monkeypatch):
        monkeypatch.setattr(
            "agente_oracle.server.auth.rotas.criar_cliente", lambda settings: _ClienteGlpiFake("infra")
        )

        resposta = mcp_app.patch(
            f"/api/auth/usuarios/{usuario_criado['id']}",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={
                "nome": "Agora de TI",
                "papeis": ["ti_infraestrutura"],
                "tecnico_glpi_id": "999",
                "email": _EMAIL_TECNICO_FAKE,
            },
        )

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["tecnico_glpi_id"] == "999"
        assert corpo["area_ti"] == "infra"

    def test_email_ja_usado_por_outra_conta_e_rejeitado(
        self, mcp_app, token_dev, usuario_criado, usuario_com_email
    ):
        resposta = mcp_app.patch(
            f"/api/auth/usuarios/{usuario_criado['id']}",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={"nome": "X", "papeis": ["financeiro"], "email": usuario_com_email["email"]},
        )

        assert resposta.status_code == 400
        assert "e-mail" in resposta.json()["erro"].lower()

    def test_email_com_letra_diferente_de_outra_conta_tambem_e_rejeitado(
        self, mcp_app, token_dev, usuario_criado, usuario_com_email
    ):
        resposta = mcp_app.patch(
            f"/api/auth/usuarios/{usuario_criado['id']}",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={"nome": "X", "papeis": ["financeiro"], "email": usuario_com_email["email"].upper()},
        )

        assert resposta.status_code == 400
