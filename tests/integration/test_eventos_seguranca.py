"""Testa a trilha de auditoria de eventos de login/administração de contas
(`tools/auth/eventos_seguranca.py`) de ponta a ponta, via HTTP — cobre tanto
o registro de cada tipo de evento quanto o acesso restrito da rota de
consulta (`GET /api/auth/eventos-seguranca`, só time de TI)."""

import uuid

import pytest

from agente_oracle.tools.auth.usuarios import LIMITE_TENTATIVAS_BLOQUEIO

pytestmark = pytest.mark.integration


def _eventos(mcp_app, token_dev):
    resposta = mcp_app.get("/api/auth/eventos-seguranca", headers={"Authorization": f"Bearer {token_dev}"})
    assert resposta.status_code == 200
    return resposta.json()


def _ultimo_evento_de(eventos, tipo, usuario_afetado):
    encontrados = [e for e in eventos if e["tipo"] == tipo and e["usuario_afetado"] == usuario_afetado]
    return encontrados[0] if encontrados else None


class TestRotaEventosSeguranca:
    def test_sem_papel_desenvolvedor_e_negado(self, mcp_app, token_teste):
        resposta = mcp_app.get(
            "/api/auth/eventos-seguranca", headers={"Authorization": f"Bearer {token_teste}"}
        )
        assert resposta.status_code == 403

    def test_sem_token_e_negado(self, mcp_app):
        resposta = mcp_app.get("/api/auth/eventos-seguranca")
        assert resposta.status_code == 401


class TestRegistroDeEventos:
    def test_login_falha_e_registrado(self, mcp_app, usuario_teste, token_dev):
        mcp_app.post("/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": "senha-errada"})

        evento = _ultimo_evento_de(_eventos(mcp_app, token_dev), "login_falha", usuario_teste["usuario"])
        assert evento is not None

    def test_login_sucesso_e_registrado(self, mcp_app, usuario_teste, token_dev):
        mcp_app.post(
            "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": usuario_teste["senha"]}
        )

        evento = _ultimo_evento_de(_eventos(mcp_app, token_dev), "login_sucesso", usuario_teste["usuario"])
        assert evento is not None

    def test_conta_bloqueada_e_registrada(self, mcp_app, usuario_teste, token_dev):
        for _ in range(LIMITE_TENTATIVAS_BLOQUEIO):
            mcp_app.post(
                "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": "senha-errada"}
            )

        evento = _ultimo_evento_de(_eventos(mcp_app, token_dev), "conta_bloqueada", usuario_teste["usuario"])
        assert evento is not None

    def test_conta_desbloqueada_e_registrada_com_quem_desbloqueou(
        self, mcp_app, usuario_teste, usuario_dev, token_dev
    ):
        for _ in range(LIMITE_TENTATIVAS_BLOQUEIO):
            mcp_app.post(
                "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": "senha-errada"}
            )

        mcp_app.patch(
            f"/api/auth/usuarios/{usuario_teste['id']}/desbloquear",
            headers={"Authorization": f"Bearer {token_dev}"},
        )

        evento = _ultimo_evento_de(
            _eventos(mcp_app, token_dev), "conta_desbloqueada", usuario_teste["usuario"]
        )
        assert evento is not None
        assert evento["realizado_por"] == usuario_dev["usuario"]

    def test_usuario_criado_e_apagado_sao_registrados(self, mcp_app, token_dev, usuario_dev):
        login = f"teste_evento_{uuid.uuid4().hex[:12]}"

        criado = mcp_app.post(
            "/api/auth/usuarios",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={
                "usuario": login,
                "senha": "SenhaDeTeste!123",
                "nome": "Teste Evento",
                "papeis": ["financeiro"],
            },
        )
        assert criado.status_code == 201
        id_criado = criado.json()["id"]

        evento_criado = _ultimo_evento_de(_eventos(mcp_app, token_dev), "usuario_criado", login)
        assert evento_criado is not None
        assert evento_criado["realizado_por"] == usuario_dev["usuario"]
        assert evento_criado["detalhes"]["papeis"] == ["financeiro"]

        apagado = mcp_app.delete(
            f"/api/auth/usuarios/{id_criado}", headers={"Authorization": f"Bearer {token_dev}"}
        )
        assert apagado.status_code == 200

        evento_apagado = _ultimo_evento_de(_eventos(mcp_app, token_dev), "usuario_apagado", login)
        assert evento_apagado is not None
        assert evento_apagado["realizado_por"] == usuario_dev["usuario"]
