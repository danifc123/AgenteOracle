from agente_oracle.agent.financeiro import projecoes as mod


class TestProjetarTendenciaLinear:
    def test_serie_perfeitamente_linear(self):
        resultado = mod.projetar_tendencia_linear([10.0, 20.0, 30.0, 40.0], 2)
        assert resultado == [50.0, 60.0]

    def test_serie_constante(self):
        resultado = mod.projetar_tendencia_linear([50.0, 50.0, 50.0], 2)
        assert resultado == [50.0, 50.0]

    def test_menos_de_dois_pontos_devolve_vazio(self):
        assert mod.projetar_tendencia_linear([], 3) == []
        assert mod.projetar_tendencia_linear([100.0], 3) == []

    def test_zero_meses_futuros_devolve_vazio(self):
        assert mod.projetar_tendencia_linear([10.0, 20.0], 0) == []


class TestProximosMeses:
    def test_mesmo_ano(self):
        assert mod.proximos_meses("2026-01", 2) == ["2026-02", "2026-03"]

    def test_virada_de_ano(self):
        assert mod.proximos_meses("2026-11", 3) == ["2026-12", "2027-01", "2027-02"]

    def test_quantidade_zero_devolve_vazio(self):
        assert mod.proximos_meses("2026-05", 0) == []
