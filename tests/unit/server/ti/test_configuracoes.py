from decimal import Decimal

import pytest

from agente_oracle.server.ti import configuracoes as configuracoes_module
from agente_oracle.server.ti.configuracoes import _modelo_valido, _percentual_valido, _teto_tokens_valido


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


class TestModeloValido:
    def test_vazio_e_aceito_significa_usar_padrao_do_provedor(self):
        assert _modelo_valido({"modelo_ia": ""}) is True

    def test_nao_string_e_rejeitado(self):
        assert _modelo_valido({"modelo_ia": 123}) is False

    def test_modelo_fixo_da_oci_aceito_quando_provedor_vem_no_mesmo_corpo(self):
        assert _modelo_valido({"provedor_ia": "oci_openai", "modelo_ia": "openai.gpt-oss-120b"}) is True

    def test_modelo_fora_da_lista_rejeitado_quando_provedor_oci_no_mesmo_corpo(self):
        assert _modelo_valido({"provedor_ia": "oci_openai", "modelo_ia": "modelo-inventado"}) is False

    def test_qualquer_texto_aceito_quando_provedor_ollama_no_mesmo_corpo(self):
        assert _modelo_valido({"provedor_ia": "ollama", "modelo_ia": "qwen2.5-coder:7b"}) is True

    def test_sem_provedor_no_corpo_usa_o_provedor_ja_configurado(self, monkeypatch):
        monkeypatch.setattr(configuracoes_module.configuracoes_provedor, "provedor_ia", lambda: "oci_openai")

        assert _modelo_valido({"modelo_ia": "modelo-inventado"}) is False

    def test_sem_provedor_no_corpo_e_ja_configurado_como_ollama_aceita_texto_livre(self, monkeypatch):
        monkeypatch.setattr(configuracoes_module.configuracoes_provedor, "provedor_ia", lambda: "ollama")

        assert _modelo_valido({"modelo_ia": "qwen2.5-coder:7b"}) is True


class TestTetoTokensValido:
    @pytest.mark.parametrize("bruto", [0, 1, 50000])
    def test_inteiro_maior_ou_igual_a_zero_e_aceito(self, bruto):
        assert _teto_tokens_valido(bruto) is True

    def test_negativo_e_rejeitado(self):
        assert _teto_tokens_valido(-1) is False

    @pytest.mark.parametrize("bruto", [True, False, None, "50000", 12.5, [50000]])
    def test_nao_inteiro_e_rejeitado_inclusive_bool(self, bruto):
        # `True` é `int` em Python — sem a checagem explícita viraria 1.
        assert _teto_tokens_valido(bruto) is False
