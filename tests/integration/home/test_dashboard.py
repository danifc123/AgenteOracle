"""Cada usuário lê/grava só o PRÓPRIO layout de widgets da Home unificada
(autoatendimento, sem {id} na URL — mesmo padrão de /api/auth/perfil)."""

import uuid

import pytest

from agente_oracle.tools.auth import layout_dashboard

pytestmark = pytest.mark.integration

_URL = "/api/home/dashboard"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _item(widget_id: str, tamanho: str = "pequeno") -> dict:
    return {"id": widget_id, "tamanho": tamanho}


@pytest.fixture
def token_ti_nao_dev(mcp_app):
    """Usuário com acesso ao módulo TI que NÃO é desenvolvedor."""
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login = f"teste_home_ti_{uuid.uuid4().hex[:12]}"
    senha = "SenhaDeTeste!123"
    criado = usuarios_tools.criar_usuario(login, senha, "TI não-dev (teste de home)", ["ti_admin"])
    try:
        resposta = mcp_app.post("/api/auth/login", json={"usuario": login, "senha": senha})
        assert resposta.status_code == 200
        yield resposta.json()["token"], criado["id"]
    finally:
        usuarios_tools.deletar_usuario(criado["id"])


@pytest.fixture
def token_financeiro_admin(mcp_app):
    """Usuário administrador do Financeiro — não é `desenvolvedor`, mas
    `papeis.eh_administrador` é `True` (testa `comum:usuarios`, que exige
    administrador de QUALQUER módulo, não um papel específico)."""
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login = f"teste_home_fin_admin_{uuid.uuid4().hex[:12]}"
    senha = "SenhaDeTeste!123"
    criado = usuarios_tools.criar_usuario(login, senha, "Admin Financeiro (teste de home)", ["financeiro_admin"])
    try:
        resposta = mcp_app.post("/api/auth/login", json={"usuario": login, "senha": senha})
        assert resposta.status_code == 200
        yield resposta.json()["token"]
    finally:
        usuarios_tools.deletar_usuario(criado["id"])


class TestLeituraSemLayoutSalvo:
    def test_devolve_lista_vazia_sem_layout_nenhum_salvo(self, mcp_app, token_teste):
        resposta = mcp_app.get(_URL, headers=_auth(token_teste))

        assert resposta.status_code == 200
        assert resposta.json()["widgets"] == []

    def test_usuario_financeiro_nao_recebe_nenhum_widget_de_ti_mesmo_migrado(self, mcp_app, token_teste):
        resposta = mcp_app.get(_URL, headers=_auth(token_teste))

        assert resposta.json()["widgets"] == []


class TestMigracaoDoLayoutAntigoDoTi:
    def test_layout_antigo_salvo_em_modulo_ti_aparece_migrado_e_namespaced(self, mcp_app, token_ti_nao_dev):
        token, usuario_id = token_ti_nao_dev
        layout_dashboard.definir_layout_dashboard(usuario_id, "ti", [_item("chamados_total", "grande")])

        resposta = mcp_app.get(_URL, headers=_auth(token))

        assert resposta.status_code == 200
        assert resposta.json()["widgets"] == [_item("ti:chamados_total", "grande")]

    def test_migracao_nao_e_gravada_de_volta_sozinha(self, mcp_app, token_ti_nao_dev):
        token, usuario_id = token_ti_nao_dev
        layout_dashboard.definir_layout_dashboard(usuario_id, "ti", [_item("chamados_total")])

        mcp_app.get(_URL, headers=_auth(token))

        assert layout_dashboard.layout_dashboard(usuario_id, "home") is None

    def test_usuario_com_layout_novo_ja_salvo_ignora_o_legado_do_ti(self, mcp_app, token_ti_nao_dev):
        token, usuario_id = token_ti_nao_dev
        layout_dashboard.definir_layout_dashboard(usuario_id, "ti", [_item("chamados_total")])
        layout_dashboard.definir_layout_dashboard(usuario_id, "home", [_item("ti:chamados_por_status", "grande")])

        resposta = mcp_app.get(_URL, headers=_auth(token))

        assert resposta.json()["widgets"] == [_item("ti:chamados_por_status", "grande")]


class TestWidgetsComuns:
    def test_widget_comum_e_salvo_e_lido_por_um_usuario_de_qualquer_papel(self, mcp_app, token_teste):
        salvou = mcp_app.put(_URL, json={"widgets": [_item("comum:central_suporte")]}, headers=_auth(token_teste))

        assert salvou.status_code == 200
        assert salvou.json()["widgets"] == [_item("comum:central_suporte")]

    def test_widget_comum_que_exige_administrador_e_descartado_pra_quem_nao_e_admin(self, mcp_app, token_teste):
        resposta = mcp_app.put(_URL, json={"widgets": [_item("comum:usuarios")]}, headers=_auth(token_teste))

        assert resposta.json()["widgets"] == []

    def test_widget_comum_que_exige_administrador_e_salvo_pra_administrador_de_qualquer_modulo(
        self, mcp_app, token_financeiro_admin
    ):
        resposta = mcp_app.put(_URL, json={"widgets": [_item("comum:usuarios")]}, headers=_auth(token_financeiro_admin))

        assert resposta.json()["widgets"] == [_item("comum:usuarios")]


class TestSalvarLayout:
    def test_put_e_get_fazem_round_trip_da_ordem_e_do_tamanho_salvos(self, mcp_app, token_dev):
        nova_ordem = [_item("ti:chamados_por_status", "grande"), _item("financeiro:saldo_projetado")]

        salvou = mcp_app.put(_URL, json={"widgets": nova_ordem}, headers=_auth(token_dev))
        assert salvou.status_code == 200
        assert salvou.json()["widgets"] == nova_ordem

        leu = mcp_app.get(_URL, headers=_auth(token_dev))
        assert leu.json()["widgets"] == nova_ordem

    def test_usuario_financeiro_salvando_widget_de_ti_e_descartado_silenciosamente(self, mcp_app, token_teste):
        resposta = mcp_app.put(
            _URL,
            json={"widgets": [_item("financeiro:saldo_projetado"), _item("ti:chamados_total")]},
            headers=_auth(token_teste),
        )

        assert resposta.status_code == 200
        assert resposta.json()["widgets"] == [_item("financeiro:saldo_projetado")]

    def test_id_duplicado_mantem_so_a_primeira_ocorrencia(self, mcp_app, token_dev):
        resposta = mcp_app.put(
            _URL,
            json={
                "widgets": [
                    _item("ti:chamados_total", "grande"),
                    _item("financeiro:saldo_projetado"),
                    _item("ti:chamados_total"),
                ]
            },
            headers=_auth(token_dev),
        )

        assert resposta.json()["widgets"] == [_item("ti:chamados_total", "grande"), _item("financeiro:saldo_projetado")]

    def test_tamanho_ausente_ou_invalido_e_normalizado_pro_padrao_do_catalogo(self, mcp_app, token_dev):
        resposta = mcp_app.put(
            _URL,
            json={"widgets": [{"id": "financeiro:saldo_projetado"}, {"id": "ti:chamados_por_status", "tamanho": "gigante"}]},
            headers=_auth(token_dev),
        )

        assert resposta.json()["widgets"] == [
            _item("financeiro:saldo_projetado", "pequeno"),
            _item("ti:chamados_por_status", "grande"),
        ]

    def test_corpo_com_item_sem_id_recebe_400(self, mcp_app, token_dev):
        resposta = mcp_app.put(_URL, json={"widgets": [{"tamanho": "pequeno"}]}, headers=_auth(token_dev))

        assert resposta.status_code == 400

    def test_salvar_layout_novo_encerra_a_migracao_do_legado_do_ti(self, mcp_app, token_ti_nao_dev):
        token, usuario_id = token_ti_nao_dev
        layout_dashboard.definir_layout_dashboard(usuario_id, "ti", [_item("chamados_total")])

        mcp_app.put(_URL, json={"widgets": [_item("ti:chamados_por_status", "grande")]}, headers=_auth(token))

        assert layout_dashboard.layout_dashboard(usuario_id, "home") == [_item("ti:chamados_por_status", "grande")]


class TestApagarUsuarioLimpaLayout:
    def test_deletar_usuario_remove_o_layout_salvo_em_home(self):
        from agente_oracle.tools.auth import usuarios as usuarios_tools

        login = f"teste_apagar_home_{uuid.uuid4().hex[:12]}"
        criado = usuarios_tools.criar_usuario(login, "SenhaDeTeste!123", "Apagar (teste home)", ["financeiro"])
        layout_dashboard.definir_layout_dashboard(criado["id"], "home", [_item("financeiro:saldo_projetado")])
        assert layout_dashboard.layout_dashboard(criado["id"], "home") == [_item("financeiro:saldo_projetado")]

        usuarios_tools.deletar_usuario(criado["id"])

        assert layout_dashboard.layout_dashboard(criado["id"], "home") is None
