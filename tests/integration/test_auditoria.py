"""Testa `/api/auditoria` e `/api/auditoria/dispensar` de ponta a ponta
contra o Postgres de teste. A análise em si depende do Ollama estar
disponível no ambiente — `analisar_perfis` já cai em lista vazia nesse caso
(mesmo fallback usado nos testes de previsão), então os testes aqui cobrem
shape/autorização/RBAC, não o conteúdo exato dos achados."""

import uuid

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
    resposta = mcp_app.get("/api/auditoria", params={"modulo": "financeiro"}, headers=_auth(token_teste))
    assert resposta.status_code == 200
    achados = resposta.json()
    assert isinstance(achados, list)
    for achado in achados:
        assert set(achado.keys()) == {"modulo", "view", "campo", "valor", "descricao"}
        # `usuario_teste` só tem o papel "financeiro" — nunca deveria ver achado de outro módulo.
        assert achado["modulo"] == "financeiro"


def test_auditoria_sem_modulo_e_rejeitado(mcp_app, token_teste):
    """Sem `?modulo=`, a rota não roda mais "todos os módulos liberados numa
    tacada só" — cada departamento precisa dizer qual auditoria quer rodar."""
    resposta = mcp_app.get("/api/auditoria", headers=_auth(token_teste))
    assert resposta.status_code == 400


def test_auditoria_modulo_fora_do_acesso_e_bloqueado(mcp_app, token_teste):
    """`usuario_teste` só tem o papel "financeiro" — não pode rodar (nem ver)
    a auditoria de um módulo que não tem acesso."""
    resposta = mcp_app.get("/api/auditoria", params={"modulo": "estoque"}, headers=_auth(token_teste))
    assert resposta.status_code == 403


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


def test_dispensados_sozinho_nao_esconde_do_get(mcp_app, token_teste, usuario_teste):
    """`ativo` é a única fonte de verdade de quem aparece no GET — chamar só
    `dispensados.dispensar` (sem passar pela rota, que também desativa) não
    é suficiente pra esconder um achado ainda ativo. Documenta o oposto do
    que valia antes de "Dispensar" passar a desativar globalmente — sem essa
    garantia, um achado com `ativo=True` podia sumir do dialog por causa de
    uma dispensa avulsa, que foi exatamente o bug relatado."""
    historico_tools.salvar(
        "usuario-qualquer",
        [
            Achado(
                modulo="financeiro",
                view="vw_teste_dispensados_sozinho",
                campo="campo",
                valor="valor-r",
                descricao="teste",
            )
        ],
    )
    dispensados.dispensar(str(usuario_teste["id"]), "financeiro", "vw_teste_dispensados_sozinho", "campo", "valor-r")

    resposta = mcp_app.get("/api/auditoria", params={"modulo": "financeiro"}, headers=_auth(token_teste))
    assert resposta.status_code == 200
    achados = resposta.json()
    assert any(
        achado["view"] == "vw_teste_dispensados_sozinho" and achado["valor"] == "valor-r" for achado in achados
    )


def test_achados_ativos_lido_antes_de_salvar_nao_inclui_o_que_esta_sendo_salvo():
    """Regressão do bug "8 no dialog, 4 na lista": `achados_ativos` lido
    ANTES de `salvar` não pode incluir o que está prestes a ser salvo — a
    rota depende dessa ordem pra `achados_novos` e `achados_ja_conhecidos`
    serem disjuntos de verdade (ver docstring de `auditoria_route`). Lido
    DEPOIS, cada achado novo apareceria duplicado.

    `valor` usa um uuid único por execução — `auditoria_historico` nunca
    expira por design, então um valor fixo faz a asserção "ainda não existe"
    falhar sozinha depois da 1ª vez que a suíte roda contra o mesmo banco."""
    valor = f"valor-ordem-{uuid.uuid4().hex[:12]}"
    tupla = ("financeiro", "vw_teste_ordem_achados_ativos", "campo", valor)

    antes = historico_tools.achados_ativos(["financeiro"])
    assert not any((a.modulo, a.view, a.campo, a.valor) == tupla for a in antes)

    historico_tools.salvar(
        "usuario-qualquer",
        [Achado(modulo="financeiro", view="vw_teste_ordem_achados_ativos", campo="campo", valor=valor, descricao="teste")],
    )

    depois = historico_tools.achados_ativos(["financeiro"])
    assert any((a.modulo, a.view, a.campo, a.valor) == tupla for a in depois)


def test_dispensar_route_tambem_desativa_globalmente(mcp_app, token_teste):
    """"Dispensar" não é mais só por usuário — a rota também chama
    `definir_ativo(..., False)`, então o achado deixa de contar em
    `ja_identificados` (a IA pode reencontrá-lo numa execução futura) e some
    da Lista de Auditoria pra todo mundo, não só pra quem dispensou."""
    historico_tools.salvar(
        "usuario-qualquer",
        [
            Achado(
                modulo="financeiro",
                view="vw_teste_dispensar_desativa",
                campo="campo",
                valor="valor-t",
                descricao="teste",
            )
        ],
    )
    assert ("financeiro", "vw_teste_dispensar_desativa", "campo", "valor-t") in historico_tools.ja_identificados()

    resposta = mcp_app.post(
        "/api/auditoria/dispensar",
        json={"modulo": "financeiro", "view": "vw_teste_dispensar_desativa", "campo": "campo", "valor": "valor-t"},
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 200
    assert (
        "financeiro",
        "vw_teste_dispensar_desativa",
        "campo",
        "valor-t",
    ) not in historico_tools.ja_identificados()


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


def test_auditoria_historico_com_modulo_filtra(mcp_app, token_teste, usuario_teste):
    historico_tools.salvar(
        str(usuario_teste["id"]),
        [Achado(modulo="financeiro", view="vw_teste_filtro_modulo", campo="campo", valor="valor-filtro", descricao="teste")],
    )

    resposta = mcp_app.get("/api/auditoria/historico", params={"modulo": "financeiro"}, headers=_auth(token_teste))
    assert resposta.status_code == 200
    registros = resposta.json()
    assert all(registro["modulo"] == "financeiro" for registro in registros)
    assert any(registro["valor"] == "valor-filtro" for registro in registros)


def test_auditoria_historico_com_modulo_fora_do_acesso_e_bloqueado(mcp_app, token_teste):
    resposta = mcp_app.get("/api/auditoria/historico", params={"modulo": "estoque"}, headers=_auth(token_teste))
    assert resposta.status_code == 403


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


def test_listar_por_padrao_nao_inclui_desativado():
    historico_tools.salvar(
        "usuario-qualquer",
        [Achado(modulo="financeiro", view="vw_teste_listar_ativo", campo="campo", valor="valor-w", descricao="teste")],
    )
    historico_tools.definir_ativo("financeiro", "vw_teste_listar_ativo", "campo", "valor-w", False)

    registros = historico_tools.listar(["financeiro"])
    assert not any(r["view"] == "vw_teste_listar_ativo" and r["valor"] == "valor-w" for r in registros)

    registros_com_desativados = historico_tools.listar(["financeiro"], incluir_desativados=True)
    assert any(r["view"] == "vw_teste_listar_ativo" and r["valor"] == "valor-w" for r in registros_com_desativados)


def test_auditoria_historico_route_usuario_comum_nao_ve_desativado(mcp_app, token_teste, usuario_teste):
    """`usuario_teste` só tem o papel "financeiro" (não "desenvolvedor") — não
    deve nem saber que um achado desativado existe."""
    historico_tools.salvar(
        str(usuario_teste["id"]),
        [Achado(modulo="financeiro", view="vw_teste_route_ativo", campo="campo", valor="valor-v", descricao="teste")],
    )
    historico_tools.definir_ativo("financeiro", "vw_teste_route_ativo", "campo", "valor-v", False)

    resposta = mcp_app.get("/api/auditoria/historico", headers=_auth(token_teste))
    registros = resposta.json()
    assert not any(r["view"] == "vw_teste_route_ativo" and r["valor"] == "valor-v" for r in registros)


def test_auditoria_historico_route_desenvolvedor_ve_desativado(mcp_app):
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    historico_tools.salvar(
        "usuario-dev-listar-teste",
        [Achado(modulo="financeiro", view="vw_teste_route_dev", campo="campo", valor="valor-u", descricao="teste")],
    )
    historico_tools.definir_ativo("financeiro", "vw_teste_route_dev", "campo", "valor-u", False)

    login = f"teste_dev_{uuid.uuid4().hex[:12]}"
    senha = "SenhaDeTeste!123"
    criado = usuarios_tools.criar_usuario(login, senha, "Dev de Teste (integração)", ["desenvolvedor"])
    try:
        resposta_login = mcp_app.post("/api/auth/login", json={"usuario": login, "senha": senha})
        token = resposta_login.json()["token"]

        resposta = mcp_app.get("/api/auditoria/historico", headers=_auth(token))
        registros = resposta.json()
        encontrado = next(
            (r for r in registros if r["view"] == "vw_teste_route_dev" and r["valor"] == "valor-u"), None
        )
        assert encontrado is not None
        assert encontrado["ativo"] is False
    finally:
        usuarios_tools.deletar_usuario(criado["id"])


def test_achados_ativos_devolve_uma_linha_por_tupla_com_a_descricao_mais_recente():
    historico_tools.salvar(
        "usuario-qualquer",
        [Achado(modulo="financeiro", view="vw_teste_ativos", campo="campo", valor="valor-x", descricao="primeira")],
    )
    historico_tools.salvar(
        "usuario-qualquer",
        [
            Achado(
                modulo="financeiro",
                view="vw_teste_ativos",
                campo="campo",
                valor="valor-x",
                descricao="segunda mais recente",
            )
        ],
    )
    encontrados = [
        achado
        for achado in historico_tools.achados_ativos(["financeiro"])
        if achado.view == "vw_teste_ativos" and achado.valor == "valor-x"
    ]
    assert len(encontrados) == 1
    assert encontrados[0].descricao == "segunda mais recente"


def test_achados_ativos_nao_inclui_desativado():
    historico_tools.salvar(
        "usuario-qualquer",
        [
            Achado(
                modulo="financeiro",
                view="vw_teste_ativos_desativado",
                campo="campo",
                valor="valor-y",
                descricao="teste",
            )
        ],
    )
    historico_tools.definir_ativo("financeiro", "vw_teste_ativos_desativado", "campo", "valor-y", False)

    ativos = historico_tools.achados_ativos(["financeiro"])
    assert not any(achado.view == "vw_teste_ativos_desativado" and achado.valor == "valor-y" for achado in ativos)


def test_achados_ativos_respeita_modulos_liberados():
    historico_tools.salvar(
        "usuario-qualquer",
        [Achado(modulo="estoque", view="vw_teste_ativos_modulo", campo="campo", valor="valor-z", descricao="teste")],
    )

    ativos_financeiro = historico_tools.achados_ativos(["financeiro"])
    assert not any(achado.view == "vw_teste_ativos_modulo" for achado in ativos_financeiro)

    ativos_estoque = historico_tools.achados_ativos(["estoque"])
    assert any(
        achado.view == "vw_teste_ativos_modulo" and achado.valor == "valor-z" for achado in ativos_estoque
    )


def test_achados_ativos_sem_modulos_devolve_vazio():
    assert historico_tools.achados_ativos([]) == []


def test_definir_ativo_desativa_e_reativa_todas_as_linhas_da_tupla():
    historico_tools.salvar(
        "usuario-teste-ativo",
        [Achado(modulo="financeiro", view="vw_teste_ativo", campo="campo", valor="valor-ativo-1", descricao="teste")],
    )
    assert ("financeiro", "vw_teste_ativo", "campo", "valor-ativo-1") in historico_tools.ja_identificados()

    assert historico_tools.definir_ativo("financeiro", "vw_teste_ativo", "campo", "valor-ativo-1", False) is True
    assert ("financeiro", "vw_teste_ativo", "campo", "valor-ativo-1") not in historico_tools.ja_identificados()

    historico_tools.definir_ativo("financeiro", "vw_teste_ativo", "campo", "valor-ativo-1", True)
    assert ("financeiro", "vw_teste_ativo", "campo", "valor-ativo-1") in historico_tools.ja_identificados()


def test_definir_ativo_sem_achado_correspondente_devolve_false():
    assert historico_tools.definir_ativo("financeiro", "vw_inexistente", "campo", "valor-que-nao-existe", False) is False


def test_historico_ativo_route_sem_token_e_nao_autorizado(mcp_app):
    resposta = mcp_app.patch(
        "/api/auditoria/historico/ativo",
        json={"modulo": "financeiro", "view": "v", "campo": "c", "valor": "x", "ativo": False},
    )
    assert resposta.status_code == 401


def test_historico_ativo_route_sem_papel_desenvolvedor_e_bloqueado(mcp_app, token_teste):
    """`usuario_teste` só tem o papel "financeiro" — mesmo sendo um achado do
    módulo que ele acessa, ativar/desativar é restrito a desenvolvedor."""
    resposta = mcp_app.patch(
        "/api/auditoria/historico/ativo",
        json={"modulo": "financeiro", "view": "vw_clientes", "campo": "filial", "valor": "1908745", "ativo": False},
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 403


def test_historico_ativo_route_com_papel_desenvolvedor_funciona(mcp_app):
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    historico_tools.salvar(
        "usuario-dev-teste",
        [Achado(modulo="financeiro", view="vw_teste_dev", campo="campo", valor="valor-dev-1", descricao="teste")],
    )

    login = f"teste_dev_{uuid.uuid4().hex[:12]}"
    senha = "SenhaDeTeste!123"
    criado = usuarios_tools.criar_usuario(login, senha, "Dev de Teste (integração)", ["desenvolvedor"])
    try:
        resposta_login = mcp_app.post("/api/auth/login", json={"usuario": login, "senha": senha})
        token = resposta_login.json()["token"]

        resposta = mcp_app.patch(
            "/api/auditoria/historico/ativo",
            json={
                "modulo": "financeiro",
                "view": "vw_teste_dev",
                "campo": "campo",
                "valor": "valor-dev-1",
                "ativo": False,
            },
            headers=_auth(token),
        )
        assert resposta.status_code == 200
        assert resposta.json() == {"ok": True}
        assert ("financeiro", "vw_teste_dev", "campo", "valor-dev-1") not in historico_tools.ja_identificados()
    finally:
        usuarios_tools.deletar_usuario(criado["id"])


def test_ja_identificados_inclui_achado_salvo_por_qualquer_usuario():
    """`ja_identificados` é global — não filtra por usuário nem por módulo
    liberado (isso é feito depois, na camada de rota/histórico); é só "isso
    já apareceu em algum momento"."""
    historico_tools.salvar(
        "usuario-qualquer-outro",
        [
            Achado(
                modulo="financeiro",
                view="vw_teste_ja_identificados",
                campo="campo",
                valor="valor-unico-123",
                descricao="teste",
            )
        ],
    )
    assert ("financeiro", "vw_teste_ja_identificados", "campo", "valor-unico-123") in historico_tools.ja_identificados()
