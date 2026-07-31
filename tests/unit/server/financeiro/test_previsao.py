import pytest

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


class TestHistoricoEProjecao:
    def test_preenche_meses_sem_dado_com_zero_e_projeta(self):
        valores_por_mes = {"2026-05": 10.0, "2026-06": 20.0, "2026-07": 30.0}
        historico, projecao = mod._historico_e_projecao(valores_por_mes, ["2026-05", "2026-06", "2026-07"], 2)
        assert historico == [
            {"mes": "2026-05", "valor": 10.0},
            {"mes": "2026-06", "valor": 20.0},
            {"mes": "2026-07", "valor": 30.0},
        ]
        assert [item["mes"] for item in projecao] == ["2026-08", "2026-09"]
        assert [item["valor"] for item in projecao] == [40.0, 50.0]

    def test_mes_sem_dado_vira_zero(self):
        historico, _ = mod._historico_e_projecao({"2026-06": 20.0}, ["2026-05", "2026-06"], 1)
        assert historico[0] == {"mes": "2026-05", "valor": 0.0}


class TestResumoParticipacoes:
    def test_media_ponderada_e_participacoes_somam_um(self):
        # cliente A: R$100 / 30 dias; cliente B: R$300 / 60 dias
        media, participacoes = mod._resumo_participacoes([(100.0, 30.0), (300.0, 60.0)])
        assert media == pytest.approx(52.5)  # (100*30 + 300*60) / 400
        assert sum(share for share, _ in participacoes) == pytest.approx(1.0)
        assert participacoes == [(0.25, 1), (0.75, 2)]

    def test_grupo_com_valor_negativo_e_descartado(self):
        media, participacoes = mod._resumo_participacoes([(100.0, 30.0), (-500.0, 60.0)])
        assert media == 30.0
        assert participacoes == [(1.0, 1)]

    def test_grupo_com_prazo_none_e_ignorado(self):
        media, participacoes = mod._resumo_participacoes([(100.0, None), (200.0, 30.0)])
        assert media == 30.0
        assert participacoes == [(1.0, 1)]

    def test_sem_grupos_cai_no_fallback(self):
        media, participacoes = mod._resumo_participacoes([])
        assert media == mod._PRAZO_MEDIO_PADRAO_DIAS
        assert participacoes == [(1.0, 1)]


class TestDistribuirEstimativaPonderada:
    def test_reparte_um_mes_entre_grupos_com_deslocamentos_diferentes(self):
        projecao = [{"mes": "2026-08", "valor": 100.0}]
        participacoes = [(0.25, 1), (0.75, 2)]
        meses_janela = ["2026-08", "2026-09", "2026-10"]
        assert mod._distribuir_estimativa_ponderada(projecao, participacoes, meses_janela) == {
            "2026-09": 25.0,
            "2026-10": 75.0,
        }

    def test_deslocamento_zero_mantem_o_mesmo_mes(self):
        projecao = [{"mes": "2026-08", "valor": 100.0}]
        assert mod._distribuir_estimativa_ponderada(projecao, [(1.0, 0)], ["2026-08"]) == {"2026-08": 100.0}

    def test_descarta_so_a_fatia_que_cai_fora_da_janela(self):
        projecao = [{"mes": "2026-08", "valor": 100.0}]
        participacoes = [(0.5, 1), (0.5, 5)]
        assert mod._distribuir_estimativa_ponderada(projecao, participacoes, ["2026-09"]) == {"2026-09": 50.0}

    def test_soma_quando_fatias_de_grupos_diferentes_caem_no_mesmo_destino(self):
        projecao = [{"mes": "2026-08", "valor": 100.0}]
        participacoes = [(0.5, 1), (0.5, 1)]
        assert mod._distribuir_estimativa_ponderada(projecao, participacoes, ["2026-09"]) == {"2026-09": 100.0}


class TestJanelaMesesHistorico:
    def test_termina_no_mes_atual_com_o_tamanho_pedido(self):
        janela = mod._janela_meses_historico(12)
        assert len(janela) == 12
        assert janela == sorted(janela)
