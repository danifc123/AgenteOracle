from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import ROUND_FLOOR, Decimal

import pytest

from agente_oracle.tools.ti import amostragem_chamados, amostragem_repositorio, configuracoes
from agente_oracle.tools.ti.amostragem_chamados import entra_na_amostra
from agente_oracle.tools.ti.amostragem_repositorio import Decisao

_AGORA = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
_ANTES = _AGORA - timedelta(days=1)
_DEPOIS = _AGORA + timedelta(hours=1)


def _simular(total_chamados: int, percentual: str) -> int:
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
        assert _simular(10, "33.333") == 3

    def test_metade_de_tres_chamados_e_um_nao_dois(self):
        assert _simular(3, "50") == 1

    def test_cem_por_cento_analisa_todos(self):
        assert _simular(10, "100") == 10

    def test_zero_por_cento_nao_analisa_nenhum(self):
        assert _simular(50, "0") == 0

    def test_chegando_um_por_vez_a_20_por_cento_o_quinto_e_o_primeiro_a_entrar(self):
        percentual = Decimal(20)
        decisoes = []
        analisados = 0

        for vistos in range(10):
            entrou = entra_na_amostra(vistos, analisados, percentual)
            decisoes.append(entrou)
            analisados += entrou

        assert decisoes == [False, False, False, False, True, False, False, False, False, True]

    def test_conta_e_exata_sem_erro_de_ponto_flutuante(self):
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


class _TransacaoFalsa:
    """Repositório em memória: registra o que o serviço pediu e gravou."""

    def __init__(self, decisoes=None, contagem=(0, 0)):
        self.decisoes = dict(decisoes or {})
        self.contagem = contagem
        self.contagens_pedidas = []
        self.gravacoes = []

    def buscar(self, chamado_id):
        return self.decisoes.get(chamado_id)

    def contar(self, percentual, regime, historico_inteiro):
        self.contagens_pedidas.append((percentual, regime, historico_inteiro))
        return self.contagem

    def gravar(self, chamado_id, decisao, percentual, ja_existe):
        self.gravacoes.append((chamado_id, decisao, percentual, ja_existe))


@pytest.fixture
def cenario(monkeypatch):
    """Monta o regime em vigor e devolve a transação falsa pra inspecionar."""

    def _montar(percentual=20, referencia=_AGORA, ler_antigos=False, decisoes=None, contagem=(0, 0)):
        transacao = _TransacaoFalsa(decisoes, contagem)
        aberturas = []

        @contextmanager
        def _abrir():
            aberturas.append(1)
            yield transacao

        monkeypatch.setattr(configuracoes, "percentual_amostragem_chamados", lambda: Decimal(str(percentual)))
        monkeypatch.setattr(configuracoes, "percentual_alterado_em", lambda: referencia)
        monkeypatch.setattr(configuracoes, "ler_chamados_antigos", lambda: ler_antigos)
        monkeypatch.setattr(amostragem_repositorio, "transacao", _abrir)
        transacao.aberturas = aberturas
        return transacao

    return _montar


class TestDeveAnalisarEmCemPorCento:
    def test_deveria_liberar_sem_abrir_transacao_quando_o_percentual_e_100(self, cenario):
        transacao = cenario(percentual=100)

        resultado = amostragem_chamados.deve_analisar(1, _ANTES)

        assert resultado is True
        assert transacao.aberturas == []


class TestDeveAnalisarChamadoNovo:
    def test_deveria_devolver_a_decisao_gravada_sem_recontar_quando_o_chamado_ja_foi_decidido(self, cenario):
        decisao = Decisao(amostrado=False, conta_na_cota=True, regime_desde=_AGORA)
        transacao = cenario(decisoes={7: decisao})

        resultado = amostragem_chamados.deve_analisar(7, _DEPOIS)

        assert resultado is False
        assert transacao.contagens_pedidas == []
        assert transacao.gravacoes == []

    def test_deveria_analisar_e_gravar_quando_o_chamado_completa_a_meta_acumulada(self, cenario):
        transacao = cenario(percentual=20, contagem=(4, 0))  # o 5º chamado a 20%

        resultado = amostragem_chamados.deve_analisar(9, _DEPOIS)

        assert resultado is True
        assert transacao.gravacoes == [
            (9, Decisao(amostrado=True, conta_na_cota=True, regime_desde=_AGORA), Decimal(20), False)
        ]

    def test_deveria_ficar_de_fora_e_gravar_quando_a_meta_acumulada_nao_foi_atingida(self, cenario):
        transacao = cenario(percentual=20, contagem=(1, 0))

        resultado = amostragem_chamados.deve_analisar(9, _DEPOIS)

        assert resultado is False
        assert transacao.gravacoes[0][1] == Decisao(amostrado=False, conta_na_cota=True, regime_desde=_AGORA)

    def test_deveria_contar_so_o_regime_atual_quando_a_flag_de_antigos_esta_desligada(self, cenario):
        transacao = cenario(percentual=20, ler_antigos=False)

        amostragem_chamados.deve_analisar(9, _DEPOIS)

        assert transacao.contagens_pedidas == [(Decimal(20), _AGORA, False)]

    def test_deveria_contar_o_historico_inteiro_quando_a_flag_de_antigos_esta_ligada(self, cenario):
        transacao = cenario(percentual=20, ler_antigos=True)

        amostragem_chamados.deve_analisar(9, _DEPOIS)

        assert transacao.contagens_pedidas == [(Decimal(20), _AGORA, True)]

    def test_deveria_tratar_como_novo_o_chamado_sem_data_de_referencia_no_regime(self, cenario):
        transacao = cenario(percentual=20, referencia=None, contagem=(4, 0))

        resultado = amostragem_chamados.deve_analisar(9, _ANTES)

        assert resultado is True
        assert transacao.gravacoes[0][1].regime_desde is None

    def test_deveria_tratar_como_novo_o_chamado_criado_exatamente_na_data_de_referencia(self, cenario):
        transacao = cenario(percentual=20, ler_antigos=False, contagem=(4, 0))

        resultado = amostragem_chamados.deve_analisar(9, _AGORA)

        assert resultado is True
        assert transacao.gravacoes[0][1].conta_na_cota is True

    def test_deveria_tratar_data_sem_fuso_como_utc(self, cenario):
        transacao = cenario(percentual=20, ler_antigos=False)
        criado_sem_fuso = _ANTES.replace(tzinfo=None)

        resultado = amostragem_chamados.deve_analisar(9, criado_sem_fuso)

        assert resultado is False
        assert transacao.gravacoes[0][1].conta_na_cota is False  # antigo: ignorado


class TestDeveAnalisarChamadoAntigoComFlagDesligada:
    def test_deveria_ignorar_sem_gastar_cota_quando_o_chamado_antigo_nunca_foi_visto(self, cenario):
        transacao = cenario(percentual=20, ler_antigos=False)

        resultado = amostragem_chamados.deve_analisar(3, _ANTES)

        assert resultado is False
        assert transacao.contagens_pedidas == []
        assert transacao.gravacoes == [
            (3, Decisao(amostrado=False, conta_na_cota=False, regime_desde=_AGORA), Decimal(20), False)
        ]

    def test_deveria_manter_a_decisao_quando_o_chamado_antigo_ja_estava_decidido(self, cenario):
        decisao = Decisao(amostrado=False, conta_na_cota=True, regime_desde=_ANTES)
        transacao = cenario(percentual=20, ler_antigos=False, decisoes={3: decisao})

        resultado = amostragem_chamados.deve_analisar(3, _ANTES)

        assert resultado is False
        assert transacao.gravacoes == []


class TestDeveAnalisarChamadoAntigoComFlagLigada:
    def test_deveria_reavaliar_uma_vez_o_antigo_que_ficou_de_fora_num_regime_anterior(self, cenario):
        decisao = Decisao(amostrado=False, conta_na_cota=True, regime_desde=_ANTES)
        transacao = cenario(percentual=50, ler_antigos=True, decisoes={3: decisao}, contagem=(10, 2))

        resultado = amostragem_chamados.deve_analisar(3, _ANTES)

        # já contado: vistos_antes = 10 - 1 → floor(10 × 50%) = 5 > 2 analisados
        assert resultado is True
        assert transacao.gravacoes == [
            (3, Decisao(amostrado=True, conta_na_cota=True, regime_desde=_AGORA), Decimal(50), True)
        ]

    def test_deveria_manter_a_decisao_quando_o_antigo_ja_foi_reavaliado_neste_regime(self, cenario):
        decisao = Decisao(amostrado=False, conta_na_cota=True, regime_desde=_AGORA)
        transacao = cenario(percentual=50, ler_antigos=True, decisoes={3: decisao})

        resultado = amostragem_chamados.deve_analisar(3, _ANTES)

        assert resultado is False
        assert transacao.gravacoes == []

    def test_deveria_contar_o_antigo_ignorado_antes_como_mais_um_chamado(self, cenario):
        decisao = Decisao(amostrado=False, conta_na_cota=False, regime_desde=_AGORA)
        transacao = cenario(percentual=20, ler_antigos=True, decisoes={3: decisao}, contagem=(4, 0))

        resultado = amostragem_chamados.deve_analisar(3, _ANTES)

        # não contado ainda: vistos_antes = 4 → é o 5º chamado a 20%
        assert resultado is True
        assert transacao.gravacoes[0][3] is True  # atualiza a linha existente

    def test_deveria_manter_analisado_o_antigo_que_ja_tinha_sido_analisado(self, cenario):
        decisao = Decisao(amostrado=True, conta_na_cota=True, regime_desde=_ANTES)
        transacao = cenario(percentual=50, ler_antigos=True, decisoes={3: decisao})

        resultado = amostragem_chamados.deve_analisar(3, _ANTES)

        assert resultado is True
        assert transacao.gravacoes == []
