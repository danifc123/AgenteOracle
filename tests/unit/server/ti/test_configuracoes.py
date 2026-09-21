from decimal import Decimal

import pytest

from agente_oracle.server.ti.configuracoes import _percentual_valido


class TestPercentualValido:
    @pytest.mark.parametrize(
        ("bruto", "esperado"),
        [
            (20, Decimal(20)),
            (0, Decimal(0)),
            (100, Decimal(100)),
            (33.333, Decimal("33.333")),
            ("33.333", Decimal("33.333")),
            (12.5, Decimal("12.5")),
        ],
    )
    def test_aceita_numero_de_0_a_100_com_ate_tres_casas(self, bruto, esperado):
        assert _percentual_valido(bruto) == esperado

    def test_float_do_json_nao_vira_dizima(self):
        # str(33.333) = "33.333" — passar o float direto pro Decimal daria
        # 33.33299999999999982946974341757595539093017578125.
        assert _percentual_valido(33.333) == Decimal("33.333")

    @pytest.mark.parametrize("bruto", [-1, -0.001, 100.001, 101, 1000])
    def test_fora_de_0_a_100_e_rejeitado(self, bruto):
        assert _percentual_valido(bruto) is None

    def test_mais_de_tres_casas_decimais_e_rejeitado(self):
        assert _percentual_valido("33.3333") is None

    def test_zeros_a_direita_nao_contam_como_casa_decimal(self):
        assert _percentual_valido("33.3330") == Decimal("33.3330")

    @pytest.mark.parametrize("bruto", ["", "abc", "NaN", "Infinity", float("inf"), float("nan")])
    def test_nao_numerico_ou_nao_finito_e_rejeitado(self, bruto):
        assert _percentual_valido(bruto) is None

    @pytest.mark.parametrize("bruto", [True, False, None, [20], {"valor": 20}])
    def test_tipo_invalido_e_rejeitado_inclusive_bool(self, bruto):
        # `True` é `int` em Python — sem a checagem explícita viraria 1%.
        assert _percentual_valido(bruto) is None
