from agente_oracle.server.financeiro import previsao as mod


class TestMesMenos:
    def test_mesmo_ano(self):
        assert mod._mes_menos("2026-07", 1) == "2026-06"

    def test_virada_de_ano(self):
        assert mod._mes_menos("2026-01", 1) == "2025-12"

    def test_onze_meses_atras(self):
        assert mod._mes_menos("2026-07", 11) == "2025-08"

    def test_zero_meses_atras_devolve_o_mesmo_mes(self):
        assert mod._mes_menos("2026-07", 0) == "2026-07"
