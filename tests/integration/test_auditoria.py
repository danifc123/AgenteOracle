"""Testa `/api/auditoria` e `/api/auditoria/dispensar` de ponta a ponta
contra o Postgres de teste. A análise em si depende do Ollama estar
disponível no ambiente — `analisar_perfis` já cai em lista vazia nesse caso
(mesmo fallback usado nos testes de previsão), então os testes aqui cobrem
shape/autorização/RBAC, não o conteúdo exato dos achados."""

import pytest

from agente_oracle.agent.auditoria.analise import Achado
from agente_oracle.tools.auditoria import dispensados
from agente_oracle.tools.auditoria import historico as historico_tools

pytestmark = pytest.mark.integration


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_auditoria_sem_token_e_nao_autorizado(mcp_app):
    resposta = mcp_app.get("/api/auditoria")
    assert resposta.status_code == 401


def test_auditoria_com_token_devolve_lista(mcp_app, token_teste):
    resposta = mcp_app.get("/api/auditoria", headers=_auth(token_teste))
    assert resposta.status_code == 200
    achados = resposta.json()
    assert isinstance(achados, list)
    for achado in achados:
        assert set(achado.keys()) == {"modulo", "view", "campo", "valor", "descricao"}
        # `usuario_teste` só tem o papel "financeiro" — nunca deveria ver achado de outro módulo.
        assert achado["modulo"] == "financeiro"


def test_dispensar_sem_token_e_nao_autorizado(mcp_app):
    resposta = mcp_app.post(
        "/api/auditoria/dispensar", json={"modulo": "financeiro", "view": "v", "campo": "c", "valor": "x"}
    )
    assert resposta.status_code == 401


def test_dispensar_corpo_incompleto_e_rejeitado(mcp_app, token_teste):
    resposta = mcp_app.post("/api/auditoria/dispensar", json={"modulo": "financeiro"}, headers=_auth(token_teste))
    assert resposta.status_code == 400


def test_dispensar_modulo_fora_do_acesso_e_bloqueado(mcp_app, token_teste):
    """`usuario_teste` só tem o papel "financeiro" — não pode dispensar achado
    de um módulo que não tem acesso, mesmo que esse módulo nem exista ainda."""
    resposta = mcp_app.post(
        "/api/auditoria/dispensar",
        json={"modulo": "estoque", "view": "vw_qualquer", "campo": "campo", "valor": "1"},
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 403


def test_dispensar_modulo_valido_e_aceito(mcp_app, token_teste):
    resposta = mcp_app.post(
        "/api/auditoria/dispensar",
        json={"modulo": "financeiro", "view": "vw_clientes", "campo": "filial", "valor": "1908745"},
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 200
    assert resposta.json() == {"ok": True}


def test_dispensar_e_idempotente(usuario_teste):
    """Chamar `dispensar` duas vezes com o mesmo achado não deve gerar erro —
    a constraint única na tabela já cobre isso via `ON CONFLICT DO NOTHING`."""
    usuario_id = str(usuario_teste["id"])
    dispensados.dispensar(usuario_id, "financeiro", "vw_clientes", "filial", "1908745")
    dispensados.dispensar(usuario_id, "financeiro", "vw_clientes", "filial", "1908745")
    assert ("financeiro", "vw_clientes", "filial", "1908745") in dispensados.listar_dispensados(usuario_id)


def test_achado_dispensado_nao_reaparece_no_get(mcp_app, token_teste, usuario_teste):
    """Dispensa um achado (independente de ele ter sido gerado pela IA ou
    não — a checagem de dispensa não sabe/precisa saber disso) e confirma que
    ele nunca aparece na resposta do GET pra esse usuário."""
    dispensados.dispensar(str(usuario_teste["id"]), "financeiro", "vw_clientes", "filial", "1908745")

    resposta = mcp_app.get("/api/auditoria", headers=_auth(token_teste))
    assert resposta.status_code == 200
    achados = resposta.json()
    assert not any(
        achado["view"] == "vw_clientes" and achado["campo"] == "filial" and achado["valor"] == "1908745"
        for achado in achados
    )


def test_auditoria_historico_sem_token_e_nao_autorizado(mcp_app):
    resposta = mcp_app.get("/api/auditoria/historico")
    assert resposta.status_code == 401


def test_auditoria_historico_lista_achados_ja_salvos(mcp_app, token_teste, usuario_teste):
    historico_tools.salvar(
        str(usuario_teste["id"]),
        [Achado(modulo="financeiro", view="vw_clientes", campo="filial", valor="1908745", descricao="achado de teste")],
    )

    resposta = mcp_app.get("/api/auditoria/historico", headers=_auth(token_teste))
    assert resposta.status_code == 200
    registros = resposta.json()
    assert any(
        registro["modulo"] == "financeiro"
        and registro["valor"] == "1908745"
        and registro["descricao"] == "achado de teste"
        for registro in registros
    )


def test_auditoria_historico_nao_mostra_achado_de_modulo_fora_do_acesso(mcp_app, token_teste, usuario_teste):
    """`usuario_teste` só tem o papel "financeiro" — achado salvo pra um
    módulo que ele não tem acesso nunca deve aparecer, nem no histórico."""
    historico_tools.salvar(
        str(usuario_teste["id"]),
        [Achado(modulo="estoque", view="vw_qualquer", campo="campo", valor="valor-secreto", descricao="teste")],
    )

    resposta = mcp_app.get("/api/auditoria/historico", headers=_auth(token_teste))
    assert resposta.status_code == 200
    registros = resposta.json()
    assert not any(registro["valor"] == "valor-secreto" for registro in registros)


def test_historico_salvar_sem_achados_nao_grava_nada():
    assert historico_tools.salvar("usuario-qualquer-sem-achado", []) is None
