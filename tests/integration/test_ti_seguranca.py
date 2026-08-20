"""Testa `/api/ti/seguranca` de ponta a ponta contra o Postgres de teste —
RBAC (só quem tem acesso ao módulo TI), histórico e dispensar. A detecção
em si depende do Ollama estar disponível no ambiente — `detectar` já cai
em lista vazia nesse caso (mesmo fallback usado nos testes de auditoria),
então os testes aqui cobrem shape/autorização, não o conteúdo exato dos
achados."""

import uuid

import pytest

from agente_oracle.agent.ti.deteccao_seguranca import AchadoSeguranca
from agente_oracle.tools.ti import historico_seguranca

pytestmark = pytest.mark.integration


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def usuario_ti_admin():
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login = f"teste_ti_admin_{uuid.uuid4().hex[:12]}"
    senha = "SenhaDeTeste!123"
    criado = usuarios_tools.criar_usuario(login, senha, "Administrador de TI (teste)", ["ti_admin"])

    yield {"usuario": login, "senha": senha, "id": criado["id"]}

    usuarios_tools.deletar_usuario(criado["id"])


@pytest.fixture
def token_ti_admin(mcp_app, usuario_ti_admin):
    resposta = mcp_app.post(
        "/api/auth/login", json={"usuario": usuario_ti_admin["usuario"], "senha": usuario_ti_admin["senha"]}
    )
    assert resposta.status_code == 200
    return resposta.json()["token"]


@pytest.fixture
def usuario_ti_infraestrutura():
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login = f"teste_ti_infra_{uuid.uuid4().hex[:12]}"
    senha = "SenhaDeTeste!123"
    criado = usuarios_tools.criar_usuario(login, senha, "Infraestrutura de TI (teste)", ["ti_infraestrutura"])

    yield {"usuario": login, "senha": senha, "id": criado["id"]}

    usuarios_tools.deletar_usuario(criado["id"])


@pytest.fixture
def token_ti_infraestrutura(mcp_app, usuario_ti_infraestrutura):
    resposta = mcp_app.post(
        "/api/auth/login",
        json={"usuario": usuario_ti_infraestrutura["usuario"], "senha": usuario_ti_infraestrutura["senha"]},
    )
    assert resposta.status_code == 200
    return resposta.json()["token"]


class TestRotaSeguranca:
    def test_sem_token_e_nao_autorizado(self, mcp_app):
        resposta = mcp_app.get("/api/ti/seguranca")
        assert resposta.status_code == 401

    def test_usuario_sem_modulo_ti_e_bloqueado(self, mcp_app, token_teste):
        resposta = mcp_app.get("/api/ti/seguranca", headers=_auth(token_teste))
        assert resposta.status_code == 403

    def test_ti_admin_roda_analise(self, mcp_app, token_ti_admin):
        resposta = mcp_app.get("/api/ti/seguranca", headers=_auth(token_ti_admin))
        assert resposta.status_code == 200
        assert isinstance(resposta.json(), list)

    def test_ti_infraestrutura_roda_analise(self, mcp_app, token_ti_infraestrutura):
        resposta = mcp_app.get("/api/ti/seguranca", headers=_auth(token_ti_infraestrutura))
        assert resposta.status_code == 200

    def test_desenvolvedor_roda_analise(self, mcp_app, token_dev):
        """`desenvolvedor` passou a pertencer ao módulo `ti` — precisa
        continuar conseguindo rodar a detecção normalmente."""
        resposta = mcp_app.get("/api/ti/seguranca", headers=_auth(token_dev))
        assert resposta.status_code == 200


class TestRotaHistorico:
    def test_sem_token_e_nao_autorizado(self, mcp_app):
        resposta = mcp_app.get("/api/ti/seguranca/historico")
        assert resposta.status_code == 401

    def test_usuario_sem_modulo_ti_e_bloqueado(self, mcp_app, token_teste):
        resposta = mcp_app.get("/api/ti/seguranca/historico", headers=_auth(token_teste))
        assert resposta.status_code == 403

    def test_lista_achados_ja_salvos(self, mcp_app, token_ti_admin):
        valor_unico = f"usuario-teste-{uuid.uuid4().hex[:12]}"
        historico_seguranca.salvar(
            "quem-rodou",
            [
                AchadoSeguranca(
                    usuario=valor_unico,
                    sistema="agente_oracle",
                    tipo="tentativa_invasao",
                    descricao="achado de teste",
                    evidencia="5 falhas",
                )
            ],
        )

        resposta = mcp_app.get("/api/ti/seguranca/historico", headers=_auth(token_ti_admin))
        assert resposta.status_code == 200
        registros = resposta.json()
        assert any(
            registro["usuario_alvo"] == valor_unico and registro["descricao"] == "achado de teste"
            for registro in registros
        )

    def test_usuario_comum_nao_ve_desativado(self, mcp_app, token_ti_admin):
        """`ti_admin` não é `desenvolvedor` — não deve ver achado
        desativado (mesma regra de `/api/auditoria/historico`)."""
        valor_unico = f"usuario-teste-{uuid.uuid4().hex[:12]}"
        historico_seguranca.salvar(
            "quem-rodou",
            [
                AchadoSeguranca(
                    usuario=valor_unico,
                    sistema="agente_oracle",
                    tipo="tentativa_invasao",
                    descricao="x",
                    evidencia="y",
                )
            ],
        )
        historico_seguranca.definir_ativo(valor_unico, "agente_oracle", "tentativa_invasao", False)

        resposta = mcp_app.get("/api/ti/seguranca/historico", headers=_auth(token_ti_admin))
        registros = resposta.json()
        assert not any(registro["usuario_alvo"] == valor_unico for registro in registros)

    def test_desenvolvedor_ve_desativado(self, mcp_app, token_dev):
        valor_unico = f"usuario-teste-{uuid.uuid4().hex[:12]}"
        historico_seguranca.salvar(
            "quem-rodou",
            [
                AchadoSeguranca(
                    usuario=valor_unico,
                    sistema="agente_oracle",
                    tipo="tentativa_invasao",
                    descricao="x",
                    evidencia="y",
                )
            ],
        )
        historico_seguranca.definir_ativo(valor_unico, "agente_oracle", "tentativa_invasao", False)

        resposta = mcp_app.get("/api/ti/seguranca/historico", headers=_auth(token_dev))
        registros = resposta.json()
        encontrado = next((r for r in registros if r["usuario_alvo"] == valor_unico), None)
        assert encontrado is not None
        assert encontrado["ativo"] is False


class TestRotaDispensar:
    def test_sem_token_e_nao_autorizado(self, mcp_app):
        resposta = mcp_app.post(
            "/api/ti/seguranca/dispensar",
            json={"usuario": "joao", "sistema": "agente_oracle", "tipo": "tentativa_invasao"},
        )
        assert resposta.status_code == 401

    def test_corpo_incompleto_e_rejeitado(self, mcp_app, token_ti_admin):
        resposta = mcp_app.post(
            "/api/ti/seguranca/dispensar", json={"usuario": "joao"}, headers=_auth(token_ti_admin)
        )
        assert resposta.status_code == 400

    def test_usuario_sem_modulo_ti_e_bloqueado(self, mcp_app, token_teste):
        resposta = mcp_app.post(
            "/api/ti/seguranca/dispensar",
            json={"usuario": "joao", "sistema": "agente_oracle", "tipo": "tentativa_invasao"},
            headers=_auth(token_teste),
        )
        assert resposta.status_code == 403

    def test_achado_inexistente_e_404(self, mcp_app, token_ti_admin):
        resposta = mcp_app.post(
            "/api/ti/seguranca/dispensar",
            json={
                "usuario": "usuario-que-nao-existe-nunca",
                "sistema": "agente_oracle",
                "tipo": "tentativa_invasao",
            },
            headers=_auth(token_ti_admin),
        )
        assert resposta.status_code == 404

    def test_dispensar_desativa_globalmente(self, mcp_app, token_ti_admin):
        valor_unico = f"usuario-teste-{uuid.uuid4().hex[:12]}"
        historico_seguranca.salvar(
            "quem-rodou",
            [
                AchadoSeguranca(
                    usuario=valor_unico,
                    sistema="agente_oracle",
                    tipo="tentativa_invasao",
                    descricao="x",
                    evidencia="y",
                )
            ],
        )
        assert (valor_unico, "agente_oracle", "tentativa_invasao") in historico_seguranca.ja_identificados()

        resposta = mcp_app.post(
            "/api/ti/seguranca/dispensar",
            json={"usuario": valor_unico, "sistema": "agente_oracle", "tipo": "tentativa_invasao"},
            headers=_auth(token_ti_admin),
        )
        assert resposta.status_code == 200
        assert (
            valor_unico,
            "agente_oracle",
            "tentativa_invasao",
        ) not in historico_seguranca.ja_identificados()
