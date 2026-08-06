"""Testa RBAC por módulo do histórico de relatórios (`GET
/api/relatorios/historico`) contra o Postgres de teste — mesmo padrão de
`test_auditoria.py`: desenvolvedor (`acesso_total`) vê o histórico de
qualquer módulo conhecido, os demais só o(s) seu(s)."""

import uuid

import pytest

from agente_oracle.tools.financeiro import historico as historico_tools

pytestmark = pytest.mark.integration


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _sql_unico() -> str:
    # `hash_sql` é único por linha (constraint) — SQL distinto por teste evita
    # colisão entre execuções (a tabela nunca expira fisicamente sem rodar
    # `salvar` de novo, então um SQL fixo colidiria em reruns).
    return f"SELECT id FROM vw_teste_historico_{uuid.uuid4().hex[:12]}"


def test_historico_lista_relatorio_do_proprio_modulo(mcp_app, token_teste):
    titulo = f"Relatório de teste {uuid.uuid4().hex[:8]}"
    historico_tools.salvar(_sql_unico(), titulo, ["id"], [[1]], modulo="financeiro")

    resposta = mcp_app.get("/api/relatorios/historico", headers=_auth(token_teste))
    assert resposta.status_code == 200
    assert any(r["titulo"] == titulo for r in resposta.json())


def test_historico_nao_mostra_relatorio_de_outro_modulo(mcp_app, token_teste):
    """`usuario_teste` só tem o papel "financeiro" — um relatório salvo com
    outro módulo (mesmo que esse módulo nem exista como papel ainda) nunca
    deve vazar pra ele."""
    titulo = f"Relatório oculto {uuid.uuid4().hex[:8]}"
    historico_tools.salvar(_sql_unico(), titulo, ["id"], [[1]], modulo="estoque")

    resposta = mcp_app.get("/api/relatorios/historico", headers=_auth(token_teste))
    assert resposta.status_code == 200
    assert not any(r["titulo"] == titulo for r in resposta.json())


def test_historico_route_usuario_estoque_e_bloqueado(mcp_app):
    """A rota mora em `server/financeiro/historico.py` e é gate por
    `exigir_modulo_financeiro` — hoje ela é uma feature exclusiva do
    Financeiro (Estoque ainda não tem a própria tela/rota de histórico), então
    um usuário só-estoque corretamente NÃO acessa isso, mesmo sem nenhum
    relatório de financeiro vazar (documenta o limite atual, não é bug)."""
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login = f"teste_estoque_{uuid.uuid4().hex[:12]}"
    senha = "SenhaDeTeste!123"
    criado = usuarios_tools.criar_usuario(login, senha, "Estoque de Teste (integração)", ["estoque"])
    try:
        resposta_login = mcp_app.post("/api/auth/login", json={"usuario": login, "senha": senha})
        token = resposta_login.json()["token"]

        resposta = mcp_app.get("/api/relatorios/historico", headers=_auth(token))
        assert resposta.status_code == 403
    finally:
        usuarios_tools.deletar_usuario(criado["id"])


def test_listar_respeita_modulos_liberados():
    titulo_financeiro = f"Relatório financeiro {uuid.uuid4().hex[:8]}"
    titulo_estoque = f"Relatório estoque {uuid.uuid4().hex[:8]}"
    historico_tools.salvar(_sql_unico(), titulo_financeiro, ["id"], [[1]], modulo="financeiro")
    historico_tools.salvar(_sql_unico(), titulo_estoque, ["id"], [[1]], modulo="estoque")

    apenas_financeiro = historico_tools.listar(["financeiro"])
    assert any(r["titulo"] == titulo_financeiro for r in apenas_financeiro)
    assert not any(r["titulo"] == titulo_estoque for r in apenas_financeiro)

    ambos = historico_tools.listar(["financeiro", "estoque"])
    assert any(r["titulo"] == titulo_financeiro for r in ambos)
    assert any(r["titulo"] == titulo_estoque for r in ambos)


def test_listar_sem_modulos_devolve_vazio():
    assert historico_tools.listar([]) == []
