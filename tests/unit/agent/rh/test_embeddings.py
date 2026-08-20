import pytest

from agente_oracle.agent.rh import embeddings as mod


class TestSimilaridadeCosseno:
    def test_vetores_identicos_dao_similaridade_maxima(self):
        assert mod.similaridade_cosseno([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)

    def test_vetores_ortogonais_dao_similaridade_zero(self):
        assert mod.similaridade_cosseno([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_vetores_opostos_dao_similaridade_minima(self):
        assert mod.similaridade_cosseno([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_escala_nao_afeta_similaridade(self):
        # Mesma direção, magnitudes diferentes — cosseno só olha o ângulo.
        assert mod.similaridade_cosseno([1.0, 1.0], [5.0, 5.0]) == pytest.approx(1.0)

    def test_vetor_nulo_devolve_zero_em_vez_de_dividir_por_zero(self):
        assert mod.similaridade_cosseno([0.0, 0.0], [1.0, 2.0]) == 0.0

    def test_dimensoes_diferentes_devolve_zero_em_vez_de_levantar_erro(self):
        assert mod.similaridade_cosseno([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0
