"""Cada usuário de TI lê/grava só o PRÓPRIO layout de indicadores da Home
(autoatendimento, sem {id} na URL — mesmo padrão de /api/auth/perfil)."""

import uuid

import pytest

from agente_oracle.server.ti.dashboard import _LAYOUT_PADRAO
from agente_oracle.tools.auth import layout_dashboard

pytestmark = pytest.mark.integration

_URL = "/api/ti/dashboard"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _item(widget_id: str, tamanho: str = "pequeno") -> dict:
    return {"id": widget_id, "tamanho": tamanho}


@pytest.fixture
def token_ti_nao_dev(mcp_app):
    """Usuário com acesso ao módulo TI que NÃO é desenvolvedor."""
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login = f"teste_ti_dash_{uuid.uuid4().hex[:12]}"
    senha = "SenhaDeTeste!123"
    criado = usuarios_tools.criar_usuario(login, senha, "TI não-dev (teste de dashboard)", ["ti_admin"])
    try:
        resposta = mcp_app.post("/api/auth/login", json={"usuario": login, "senha": senha})
        assert resposta.status_code == 200
        yield resposta.json()["token"], criado["id"]
    finally:
        usuarios_tools.deletar_usuario(criado["id"])


class TestLeituraSemLayoutSalvo:
    def test_devolve_o_layout_padrao(self, mcp_app, token_dev):
        resposta = mcp_app.get(_URL, headers=_auth(token_dev))

        assert resposta.status_code == 200
        assert resposta.json()["widgets"] == _LAYOUT_PADRAO

    def test_nao_desenvolvedor_recebe_o_padrao_ja_sem_os_indicadores_de_ia(self, mcp_app, token_ti_nao_dev):
        token, _ = token_ti_nao_dev

        resposta = mcp_app.get(_URL, headers=_auth(token))

        assert resposta.status_code == 200
        widgets = resposta.json()["widgets"]
        assert widgets
        assert not any(item["id"].startswith("ia_") for item in widgets)

    def test_indicador_de_seguranca_esta_no_padrao_pra_nao_desenvolvedor(self, mcp_app, token_ti_nao_dev):
        token, _ = token_ti_nao_dev

        resposta = mcp_app.get(_URL, headers=_auth(token))

        ids = [item["id"] for item in resposta.json()["widgets"]]
        assert "seguranca_achados_ativos" in ids


class TestSalvarLayout:
    def test_put_e_get_fazem_round_trip_da_ordem_e_do_tamanho_salvos(self, mcp_app, token_dev):
        nova_ordem = [_item("chamados_por_status", "grande"), _item("chamados_total")]

        salvou = mcp_app.put(_URL, json={"widgets": nova_ordem}, headers=_auth(token_dev))
        assert salvou.status_code == 200
        assert salvou.json()["widgets"] == nova_ordem

        leu = mcp_app.get(_URL, headers=_auth(token_dev))
        assert leu.json()["widgets"] == nova_ordem

    def test_id_duplicado_mantem_so_a_primeira_ocorrencia(self, mcp_app, token_dev):
        resposta = mcp_app.put(
            _URL,
            json={"widgets": [_item("chamados_total", "grande"), _item("chamados_por_status"), _item("chamados_total")]},
            headers=_auth(token_dev),
        )

        assert resposta.json()["widgets"] == [_item("chamados_total", "grande"), _item("chamados_por_status")]

    def test_tamanho_ausente_ou_invalido_e_normalizado_pro_padrao_do_catalogo(self, mcp_app, token_dev):
        resposta = mcp_app.put(
            _URL,
            json={"widgets": [{"id": "chamados_total"}, {"id": "chamados_por_status", "tamanho": "gigante"}]},
            headers=_auth(token_dev),
        )

        assert resposta.json()["widgets"] == [_item("chamados_total", "pequeno"), _item("chamados_por_status", "grande")]

    def test_reordenar_o_mesmo_conjunto_persiste_a_nova_ordem(self, mcp_app, token_dev):
        mcp_app.put(
            _URL, json={"widgets": [_item("chamados_total"), _item("chamados_por_status")]}, headers=_auth(token_dev)
        )

        mcp_app.put(
            _URL, json={"widgets": [_item("chamados_por_status"), _item("chamados_total")]}, headers=_auth(token_dev)
        )

        leu = mcp_app.get(_URL, headers=_auth(token_dev))
        assert leu.json()["widgets"] == [_item("chamados_por_status"), _item("chamados_total")]

    def test_nao_desenvolvedor_salvando_indicador_de_ia_e_descartado_silenciosamente(
        self, mcp_app, token_ti_nao_dev
    ):
        token, _ = token_ti_nao_dev

        resposta = mcp_app.put(
            _URL, json={"widgets": [_item("chamados_total"), _item("ia_tokens_hoje")]}, headers=_auth(token)
        )

        assert resposta.status_code == 200
        assert resposta.json()["widgets"] == [_item("chamados_total")]

    def test_nao_desenvolvedor_consegue_salvar_o_indicador_de_seguranca(self, mcp_app, token_ti_nao_dev):
        token, _ = token_ti_nao_dev

        resposta = mcp_app.put(
            _URL, json={"widgets": [_item("seguranca_achados_ativos", "grande")]}, headers=_auth(token)
        )

        assert resposta.json()["widgets"] == [_item("seguranca_achados_ativos", "grande")]

    def test_corpo_com_item_sem_id_recebe_400(self, mcp_app, token_dev):
        resposta = mcp_app.put(_URL, json={"widgets": [{"tamanho": "pequeno"}]}, headers=_auth(token_dev))

        assert resposta.status_code == 400


class TestAcessoNegado:
    def test_usuario_sem_modulo_ti_recebe_403_no_get(self, mcp_app, token_teste):
        resposta = mcp_app.get(_URL, headers=_auth(token_teste))

        assert resposta.status_code == 403

    def test_usuario_sem_modulo_ti_recebe_403_no_put(self, mcp_app, token_teste):
        resposta = mcp_app.put(_URL, json={"widgets": [_item("chamados_total")]}, headers=_auth(token_teste))

        assert resposta.status_code == 403


class TestApagarUsuarioLimpaLayout:
    def test_deletar_usuario_remove_o_layout_salvo(self):
        from agente_oracle.tools.auth import usuarios as usuarios_tools

        login = f"teste_apagar_dash_{uuid.uuid4().hex[:12]}"
        criado = usuarios_tools.criar_usuario(login, "SenhaDeTeste!123", "Apagar (teste dashboard)", ["ti_admin"])
        layout_dashboard.definir_layout_dashboard(criado["id"], "ti", [_item("chamados_total")])
        assert layout_dashboard.layout_dashboard(criado["id"], "ti") == [_item("chamados_total")]

        usuarios_tools.deletar_usuario(criado["id"])

        assert layout_dashboard.layout_dashboard(criado["id"], "ti") is None
