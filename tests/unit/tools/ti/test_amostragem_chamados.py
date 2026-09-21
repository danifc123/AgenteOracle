from decimal import ROUND_FLOOR, Decimal

import pytest

from agente_oracle.tools.ti import amostragem_chamados
from agente_oracle.tools.ti.amostragem_chamados import entra_na_amostra


def _simular(total_chamados: int, percentual: str) -> int:
    """Passa `total_chamados` chamados, um por vez, pela regra — igual ao que
    `deve_analisar` faz em produção — e devolve quantos entraram."""
    percentual_decimal = Decimal(percentual)
    analisados = 0
    for vistos in range(total_chamados):
        if entra_na_amostra(vistos, analisados, percentual_decimal):
            analisados += 1
    return analisados


class TestEntraNaAmostra:
    def test_dez_chamados_a_20_por_cento_analisam_dois(self):
        assert _simular(10, "20") == 2

    def test_percentual_quebrado_arredonda_pra_baixo_nunca_pra_cima(self):
        # 33,333% de 10 = 3,3333 → 3 (nunca 4).
        assert _simular(10, "33.333") == 3

    def test_metade_de_tres_chamados_e_um_nao_dois(self):
        # 50% de 3 = 1,5 → 1 (arredondar pra cima daria 2).
        assert _simular(3, "50") == 1

    def test_cem_por_cento_analisa_todos(self):
        assert _simular(10, "100") == 10

    def test_zero_por_cento_nao_analisa_nenhum(self):
        assert _simular(50, "0") == 0

    def test_chegando_um_por_vez_a_20_por_cento_o_quinto_e_o_primeiro_a_entrar(self):
        # Caso do webhook: um chamado por chamada — uma conta por lote daria
        # floor(0,2) = 0 pra sempre, a acumulada converge.
        percentual = Decimal(20)
        decisoes = []
        analisados = 0
        for vistos in range(10):
            entrou = entra_na_amostra(vistos, analisados, percentual)
            decisoes.append(entrou)
            analisados += entrou
        assert decisoes == [False, False, False, False, True, False, False, False, False, True]

    def test_conta_e_exata_sem_erro_de_ponto_flutuante(self):
        # Com float, 0.29 * 100 = 28.999999999999996 e o floor perderia um.
        assert _simular(100, "29") == 29

    @pytest.mark.parametrize("percentual", ["1", "7.5", "20", "33.333", "50", "66.667", "99.999"])
    def test_total_analisado_e_sempre_o_floor_da_conta_em_qualquer_ponto(self, percentual):
        percentual_decimal = Decimal(percentual)
        analisados = 0
        for vistos_antes in range(250):
            if entra_na_amostra(vistos_antes, analisados, percentual_decimal):
                analisados += 1
            esperado = int(
                ((vistos_antes + 1) * percentual_decimal / 100).to_integral_value(rounding=ROUND_FLOOR)
            )
            assert analisados == esperado


class TestDeveAnalisar:
    def test_cem_por_cento_nem_toca_o_banco_de_decisoes(self, monkeypatch):
        monkeypatch.setattr(
            amostragem_chamados.configuracoes, "percentual_amostragem_chamados", lambda: Decimal(100)
        )

        def _conexao_proibida():
            raise AssertionError("100% não deveria consultar ti_amostragem_chamados")

        monkeypatch.setattr(amostragem_chamados, "get_postgres_connection", _conexao_proibida)

        assert amostragem_chamados.deve_analisar(123) is True
