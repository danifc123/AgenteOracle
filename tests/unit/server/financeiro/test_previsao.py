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


class TestDistribuirEstimativa:
    def test_desloca_o_mes_pelo_deslocamento_informado(self):
        projecao = [{"mes": "2026-08", "valor": 100.0}]
        meses_janela = ["2026-07", "2026-08", "2026-09", "2026-10"]
        assert mod._distribuir_estimativa(projecao, 1, meses_janela) == {"2026-09": 100.0}

    def test_deslocamento_zero_mantem_o_mesmo_mes(self):
        projecao = [{"mes": "2026-08", "valor": 100.0}]
        assert mod._distribuir_estimativa(projecao, 0, ["2026-08"]) == {"2026-08": 100.0}

    def test_descarta_o_que_cai_fora_da_janela(self):
        projecao = [{"mes": "2026-12", "valor": 100.0}]
        meses_janela = ["2026-07", "2026-08"]
        assert mod._distribuir_estimativa(projecao, 1, meses_janela) == {}

    def test_soma_quando_dois_meses_caem_no_mesmo_destino(self):
        projecao = [{"mes": "2026-07", "valor": 50.0}, {"mes": "2026-08", "valor": 30.0}]
        meses_janela = ["2026-07", "2026-08", "2026-09"]
        assert mod._distribuir_estimativa(projecao, 1, meses_janela) == {"2026-08": 50.0, "2026-09": 30.0}


class TestJanelaMesesHistorico:
    def test_termina_no_mes_atual_com_o_tamanho_pedido(self):
        janela = mod._janela_meses_historico(12)
        assert len(janela) == 12
        assert janela == sorted(janela)
