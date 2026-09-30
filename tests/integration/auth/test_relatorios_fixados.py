"""Testa `/api/relatorios-fixados/{modulo}` de ponta a ponta contra o
Postgres de teste — autoatendimento aberto a qualquer usuário autenticado
(mesmo `usuario_teste`/`token_teste` compartilhados, papel `financeiro`,
usados só porque já existem no `conftest.py`; a rota em si não checa
módulo nenhum, ver `server/auth/relatorios_fixados.py`). Reaproveita
`tools/auth/layout_dashboard.py` — mesma tabela que `server/home/
dashboard.py` já usa, só com outro `modulo`."""

import uuid

import pytest

from agente_oracle.tools.auth import layout_dashboard

pytestmark = pytest.mark.integration

_URL = "/api/relatorios-fixados/financeiro:cadastros:fixados"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestRotaRelatoriosFixados:
    def test_lista_vazia_quando_nada_fixado(self, mcp_app, token_teste):
        resposta = mcp_app.get(_URL, headers=_auth(token_teste))

        assert resposta.status_code == 200
        assert resposta.json() == {"nomes": []}

    def test_fixar_um_relatorio_e_ele_aparece_na_listagem(self, mcp_app, token_teste):
        resposta = mcp_app.put(_URL, json={"nomes": ["FINR10"]}, headers=_auth(token_teste))

        assert resposta.status_code == 200
        assert resposta.json() == {"nomes": ["FINR10"]}

        resposta = mcp_app.get(_URL, headers=_auth(token_teste))
        assert resposta.json() == {"nomes": ["FINR10"]}

    def test_salvar_de_novo_substitui_a_lista_inteira(self, mcp_app, token_teste):
        mcp_app.put(_URL, json={"nomes": ["FINR10", "FINR20"]}, headers=_auth(token_teste))

        resposta = mcp_app.put(_URL, json={"nomes": ["FINR20"]}, headers=_auth(token_teste))

        assert resposta.json() == {"nomes": ["FINR20"]}

    def test_ordem_da_lista_e_preservada(self, mcp_app, token_teste):
        resposta = mcp_app.put(_URL, json={"nomes": ["FINR30", "FINR10", "FINR20"]}, headers=_auth(token_teste))

        assert resposta.json() == {"nomes": ["FINR30", "FINR10", "FINR20"]}

    def test_corpo_sem_lista_de_strings_recebe_400(self, mcp_app, token_teste):
        resposta = mcp_app.put(_URL, json={"nomes": "FINR10"}, headers=_auth(token_teste))
        assert resposta.status_code == 400

        resposta = mcp_app.put(_URL, json={"nomes": [1, 2]}, headers=_auth(token_teste))
        assert resposta.status_code == 400

        resposta = mcp_app.put(_URL, json={}, headers=_auth(token_teste))
        assert resposta.status_code == 400

    def test_fixados_de_um_modulo_nao_aparecem_em_outro(self, mcp_app, token_teste):
        mcp_app.put(_URL, json={"nomes": ["FINR10"]}, headers=_auth(token_teste))

        resposta = mcp_app.get(
            "/api/relatorios-fixados/financeiro:movimentos:fixados", headers=_auth(token_teste)
        )

        assert resposta.json() == {"nomes": []}

    def test_fixados_de_um_usuario_nao_aparecem_pra_outro(self, mcp_app, token_teste, token_dev):
        mcp_app.put(_URL, json={"nomes": ["FINR10"]}, headers=_auth(token_teste))

        resposta = mcp_app.get(_URL, headers=_auth(token_dev))
        assert resposta.json() == {"nomes": []}

    def test_sem_token_e_nao_autorizado(self, mcp_app):
        resposta = mcp_app.get(_URL)
        assert resposta.status_code == 401


class TestApagarUsuarioLimpaRelatoriosFixados:
    def test_deletar_usuario_remove_os_fixados(self):
        from agente_oracle.tools.auth import usuarios as usuarios_tools

        login = f"teste_apagar_fixados_{uuid.uuid4().hex[:12]}"
        criado = usuarios_tools.criar_usuario(login, "SenhaDeTeste!123", "Apagar (teste fixados)", ["financeiro"])
        layout_dashboard.definir_layout_dashboard(
            criado["id"], "financeiro:cadastros:fixados", [{"nome": "FINR10"}]
        )
        assert layout_dashboard.layout_dashboard(criado["id"], "financeiro:cadastros:fixados") == [
            {"nome": "FINR10"}
        ]

        usuarios_tools.deletar_usuario(criado["id"])

        assert layout_dashboard.layout_dashboard(criado["id"], "financeiro:cadastros:fixados") is None
