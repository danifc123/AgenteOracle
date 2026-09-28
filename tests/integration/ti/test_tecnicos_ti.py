"""Testa `GET /api/ti/tecnicos` — não toca o GLPI (só lê `tools/ti/tecnicos.py`
a partir do cadastro de usuário), por isso dá pra testar contra o Postgres de
teste sem mockar cliente nenhum."""

import uuid

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def tecnico_de_ti():
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login = f"teste_tecnico_{uuid.uuid4().hex[:12]}"
    criado = usuarios_tools.criar_usuario(
        login,
        "SenhaDeTeste!123",
        "Técnico de Teste",
        ["ti_infraestrutura"],
        tecnico_glpi_id="12345",
        area_ti="infra",
    )

    yield {"login": login, "id": criado["id"], "tecnico_glpi_id": "12345"}

    usuarios_tools.deletar_usuario(criado["id"])


def test_inclui_o_login_e_a_area_do_agenteoracle_de_cada_tecnico(mcp_app, token_dev, tecnico_de_ti):
    # `usuario` (login do AgenteOracle, não do GLPI) e `area` são o que o
    # front usa pro filtro "Meus chamados" — acha a área do técnico logado
    # (compara com `sessao.usuario()`) e filtra os chamados por ela, já que
    # `tecnico_atribuido` nunca aparece preenchido nesta tela — 2026-09-28.
    resposta = mcp_app.get("/api/ti/tecnicos", headers={"Authorization": f"Bearer {token_dev}"})

    assert resposta.status_code == 200
    tecnico = next(
        (item for item in resposta.json() if item["identificador"] == tecnico_de_ti["tecnico_glpi_id"]),
        None,
    )
    assert tecnico is not None
    assert tecnico["usuario"] == tecnico_de_ti["login"]
    assert tecnico["area"] == "infra"
