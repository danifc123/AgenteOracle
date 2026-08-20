from agente_oracle.agent.financeiro.simulacao_monte_carlo import (
    probabilidade_caixa_negativo,
    resumir_percentis,
    simular_cenarios,
    variacoes_mensais,
)


class TestVariacoesMensais:
    def test_calcula_diferenca_mes_a_mes(self):
        assert variacoes_mensais([100.0, 120.0, 90.0]) == [20.0, -30.0]

    def test_serie_com_um_ponto_nao_tem_variacao(self):
        assert variacoes_mensais([100.0]) == []


class TestSimularCenarios:
    def test_menos_de_dois_meses_retorna_vazio(self):
        assert simular_cenarios([100.0], meses_futuros=6, num_simulacoes=100) == []

    def test_formato_da_matriz(self):
        serie = [100.0, 110.0, 90.0, 105.0]
        matriz = simular_cenarios(serie, meses_futuros=6, num_simulacoes=50, semente=1)
        assert len(matriz) == 50
        assert all(len(caminho) == 6 for caminho in matriz)

    def test_mesma_semente_produz_mesmo_resultado(self):
        serie = [100.0, 110.0, 90.0, 105.0]
        primeira = simular_cenarios(serie, meses_futuros=6, num_simulacoes=50, semente=42)
        segunda = simular_cenarios(serie, meses_futuros=6, num_simulacoes=50, semente=42)
        assert primeira == segunda

    def test_caminho_so_usa_variacoes_ja_observadas_no_historico(self):
        serie = [100.0, 110.0, 90.0]
        variacoes_possiveis = set(variacoes_mensais(serie))
        matriz = simular_cenarios(serie, meses_futuros=4, num_simulacoes=20, semente=7)
        for caminho in matriz:
            valores = [serie[-1], *caminho]
            deltas = [atual - anterior for anterior, atual in zip(valores, valores[1:], strict=False)]
            assert all(delta in variacoes_possiveis for delta in deltas)


class TestResumirPercentis:
    def test_matriz_vazia_retorna_vazio(self):
        assert resumir_percentis([]) == []

    def test_percentis_de_uma_coluna_conhecida(self):
        # 5 simulações, 1 mês futuro: valores já ordenados 10..50.
        matriz = [[10.0], [20.0], [30.0], [40.0], [50.0]]
        resumo = resumir_percentis(matriz)
        assert len(resumo) == 1
        banda = resumo[0]
        assert banda["minimo"] == 10.0
        assert banda["maximo"] == 50.0
        assert banda["mediana"] == 30.0
        assert banda["p10"] == 14.0
        assert banda["p90"] == 46.0

    def test_duas_colunas_sao_resumidas_independentemente(self):
        matriz = [[10.0, 100.0], [20.0, 200.0]]
        resumo = resumir_percentis(matriz)
        assert len(resumo) == 2
        assert resumo[0]["mediana"] == 15.0
        assert resumo[1]["mediana"] == 150.0


class TestProbabilidadeCaixaNegativo:
    def test_sem_simulacoes_retorna_zero(self):
        assert probabilidade_caixa_negativo([]) == 0.0

    def test_conta_apenas_caminhos_com_algum_mes_negativo(self):
        matriz = [[10.0, -5.0], [20.0, 30.0], [-1.0, 50.0]]
        assert probabilidade_caixa_negativo(matriz) == 2 / 3

    def test_nenhum_caminho_negativo(self):
        matriz = [[10.0, 20.0], [5.0, 15.0]]
        assert probabilidade_caixa_negativo(matriz) == 0.0
