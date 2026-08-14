from agente_oracle.agent.financeiro import auditoria as mod


def test_views_com_filial_nao_inclui_cadastro():
    # vw_clientes/vw_fornecedores (_VIEWS_CADASTRO) não têm coluna `filial`
    # na view real (db/views/financeiro_science.sql) — se aparecessem em
    # _VIEWS_COM_FILIAL, construir_perfis_financeiro tentaria
    # `SELECT filial FROM vw_clientes` e quebraria com ORA-00904.
    assert not set(mod._VIEWS_COM_FILIAL) & set(mod._VIEWS_CADASTRO)
