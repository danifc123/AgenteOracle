"""Testa o vínculo de técnico do GLPI no cadastro de usuário
(`usuarios_route`, `POST /api/auth/usuarios`) — `buscar_area_do_tecnico`
(GLPI real) é mockado de propósito, pra não depender do GLPI de
homologação estar no ar durante o teste."""

import uuid

import pytest

pytestmark = pytest.mark.integration


class _ClienteGlpiFake:
    def __init__(self, area):
        self._area = area

    async def buscar_area_do_tecnico(self, usuario_id):
        return self._area


class TestVinculoTecnicoGlpi:
    def test_tecnico_valido_resolve_area_e_grava(self, mcp_app, token_dev, monkeypatch):
        monkeypatch.setattr(
            "agente_oracle.server.auth.rotas.criar_cliente", lambda settings: _ClienteGlpiFake("infra")
        )
        login = f"teste_{uuid.uuid4().hex[:12]}"

        resposta = mcp_app.post(
            "/api/auth/usuarios",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={
                "usuario": login,
                "senha": "SenhaOk12",
                "nome": "Teste Técnico GLPI",
                "papeis": ["ti_infraestrutura"],
                "tecnico_glpi_id": "999",
            },
        )

        assert resposta.status_code == 201
        corpo = resposta.json()
        assert corpo["tecnico_glpi_id"] == "999"
        assert corpo["area_ti"] == "infra"

        mcp_app.delete(f"/api/auth/usuarios/{corpo['id']}", headers={"Authorization": f"Bearer {token_dev}"})

    def test_tecnico_sem_area_reconhecida_e_rejeitado(self, mcp_app, token_dev, monkeypatch):
        monkeypatch.setattr(
            "agente_oracle.server.auth.rotas.criar_cliente", lambda settings: _ClienteGlpiFake(None)
        )
        login = f"teste_{uuid.uuid4().hex[:12]}"

        resposta = mcp_app.post(
            "/api/auth/usuarios",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={
                "usuario": login,
                "senha": "SenhaOk12",
                "nome": "Teste Técnico Sem Área",
                "papeis": ["ti_infraestrutura"],
                "tecnico_glpi_id": "999",
            },
        )

        assert resposta.status_code == 400
        assert "área" in resposta.json()["erro"].lower()

    def test_papel_bate_com_area_descoberta_cria_normal(self, mcp_app, token_dev, monkeypatch):
        monkeypatch.setattr(
            "agente_oracle.server.auth.rotas.criar_cliente", lambda settings: _ClienteGlpiFake("sistemas")
        )
        login = f"teste_{uuid.uuid4().hex[:12]}"

        resposta = mcp_app.post(
            "/api/auth/usuarios",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={
                "usuario": login,
                "senha": "SenhaOk12",
                "nome": "Teste Papel Bate Com Área",
                "papeis": ["ti_sistemas"],
                "tecnico_glpi_id": "999",
            },
        )

        assert resposta.status_code == 201
        corpo = resposta.json()
        assert corpo["area_ti"] == "sistemas"

        mcp_app.delete(f"/api/auth/usuarios/{corpo['id']}", headers={"Authorization": f"Bearer {token_dev}"})

    def test_papel_nao_bate_com_area_descoberta_e_rejeitado(self, mcp_app, token_dev, monkeypatch):
        # Caso real que motivou essa validação: usuário "Carlos Teste"
        # cadastrado com papel "Infraestrutura de TI", mas o grupo técnico
        # real dele no GLPI resolveu pra área "sistemas" — ninguém percebeu
        # até o painel de saúde do roster mostrar ele na área errada.
        monkeypatch.setattr(
            "agente_oracle.server.auth.rotas.criar_cliente", lambda settings: _ClienteGlpiFake("sistemas")
        )
        login = f"teste_{uuid.uuid4().hex[:12]}"

        resposta = mcp_app.post(
            "/api/auth/usuarios",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={
                "usuario": login,
                "senha": "SenhaOk12",
                "nome": "Teste Papel Não Bate",
                "papeis": ["ti_infraestrutura"],
                "tecnico_glpi_id": "999",
            },
        )

        assert resposta.status_code == 400
        assert "Sistemas de TI" in resposta.json()["erro"]

    def test_ti_admin_fica_isento_da_checagem_de_papel_por_area(self, mcp_app, token_dev, monkeypatch):
        monkeypatch.setattr(
            "agente_oracle.server.auth.rotas.criar_cliente", lambda settings: _ClienteGlpiFake("sistemas")
        )
        login = f"teste_{uuid.uuid4().hex[:12]}"

        resposta = mcp_app.post(
            "/api/auth/usuarios",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={
                "usuario": login,
                "senha": "SenhaOk12",
                "nome": "Teste Ti Admin Isento",
                "papeis": ["ti_admin"],
                "tecnico_glpi_id": "999",
            },
        )

        assert resposta.status_code == 201
        corpo = resposta.json()
        assert corpo["area_ti"] == "sistemas"

        mcp_app.delete(f"/api/auth/usuarios/{corpo['id']}", headers={"Authorization": f"Bearer {token_dev}"})

    def test_sem_tecnico_glpi_id_cria_normal_sem_chamar_glpi(self, mcp_app, token_dev, monkeypatch):
        def _nao_deveria_chamar(_settings):
            raise AssertionError("criar_cliente não deveria ser chamado sem tecnico_glpi_id")

        monkeypatch.setattr("agente_oracle.server.auth.rotas.criar_cliente", _nao_deveria_chamar)
        login = f"teste_{uuid.uuid4().hex[:12]}"

        resposta = mcp_app.post(
            "/api/auth/usuarios",
            headers={"Authorization": f"Bearer {token_dev}"},
            json={
                "usuario": login,
                "senha": "SenhaOk12",
                "nome": "Teste Sem Técnico",
                "papeis": ["ti_infraestrutura"],
            },
        )

        assert resposta.status_code == 201
        corpo = resposta.json()
        assert corpo["tecnico_glpi_id"] is None
        assert corpo["area_ti"] is None

        mcp_app.delete(f"/api/auth/usuarios/{corpo['id']}", headers={"Authorization": f"Bearer {token_dev}"})
