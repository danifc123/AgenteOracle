from agente_oracle.agent.financeiro import auditoria as mod


def test_views_com_filial_nao_inclui_cadastro():
    # vwia_clientes/vwia_fornecedores (_VIEWS_CADASTRO) não têm coluna `filial`
    # na view real (db/views/financeiro_science.sql) — se aparecessem em
    # _VIEWS_COM_FILIAL, construir_perfis_financeiro tentaria
    # `SELECT filial FROM vwia_clientes` e quebraria com ORA-00904.
    assert not set(mod._VIEWS_COM_FILIAL) & set(mod._VIEWS_CADASTRO)


class TestAchadosAPartirDasLinhas:
    def test_monta_achado_com_campos_certos(self):
        linhas = [("000123", "1", "01", "PROD1", "Fertilizante X", -5.0, -18.5)]
        achados = mod._achados_a_partir_das_linhas(linhas)

        assert len(achados) == 1
        achado = achados[0]
        assert achado.modulo == "financeiro"
        assert achado.view == "vwia_faturamento"
        assert achado.campo == "desvio_percentual"
        assert achado.valor == "NF 000123/1 item 01"
        assert "Fertilizante X" in achado.descricao
        assert "18.5" in achado.descricao

    def test_valor_identifica_a_venda_nao_so_o_produto(self):
        # Duas vendas do MESMO produto precisam gerar `valor` diferente
        # (NF/item), senão a segunda seria tratada como "já conhecida" pelo
        # dedup de `ja_identificados` mesmo sendo uma venda distinta.
        linhas = [
            ("000123", "1", "01", "PROD1", "Fertilizante X", -5.0, -18.5),
            ("000456", "1", "01", "PROD1", "Fertilizante X", -6.0, -20.0),
        ]
        achados = mod._achados_a_partir_das_linhas(linhas)
        assert achados[0].valor != achados[1].valor

    def test_lista_vazia_devolve_lista_vazia(self):
        assert mod._achados_a_partir_das_linhas([]) == []
