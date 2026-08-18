from datetime import date

from agente_oracle.agent.financeiro.otimizador_pagamento import (
    TituloPagarAberto,
    TituloPagarLiquidado,
    perfil_por_fornecedor,
    recomendar_pagamentos,
)


def _liquidado(
    fornecedor_codigo: str = "F1",
    fornecedor_nome: str = "Fornecedor Um",
    valor_original: float = 1000.0,
    data_vencimento: date = date(2026, 1, 20),
    data_baixa: date = date(2026, 1, 20),
    valor_desconto: float = 0.0,
    valor_multa: float = 0.0,
    valor_juros: float = 0.0,
) -> TituloPagarLiquidado:
    return TituloPagarLiquidado(
        fornecedor_codigo=fornecedor_codigo,
        fornecedor_nome=fornecedor_nome,
        valor_original=valor_original,
        data_vencimento=data_vencimento,
        data_baixa=data_baixa,
        valor_desconto=valor_desconto,
        valor_multa=valor_multa,
        valor_juros=valor_juros,
    )


def _aberto(
    fornecedor_codigo: str = "F1",
    fornecedor_nome: str = "Fornecedor Um",
    valor_original: float = 1000.0,
    data_vencimento: date | None = date(2026, 3, 20),
) -> TituloPagarAberto:
    return TituloPagarAberto(
        fornecedor_codigo=fornecedor_codigo,
        fornecedor_nome=fornecedor_nome,
        prefixo="A",
        numero="1",
        parcela="01",
        valor_original=valor_original,
        data_vencimento=data_vencimento,
    )


class TestPerfilPorFornecedor:
    def test_fornecedor_com_padrao_de_desconto(self):
        liquidados = [
            _liquidado(data_vencimento=date(2026, 1, 20), data_baixa=date(2026, 1, 15), valor_desconto=20.0),
            _liquidado(data_vencimento=date(2026, 2, 20), data_baixa=date(2026, 2, 15), valor_desconto=20.0),
        ]
        perfis = perfil_por_fornecedor(liquidados)
        perfil = perfis["F1"]
        assert perfil.concede_desconto is True
        assert perfil.dias_antecedencia_medio == 5.0
        assert perfil.percentual_desconto_medio == 2.0
        assert perfil.cobra_penalidade is False

    def test_fornecedor_com_padrao_de_penalidade(self):
        liquidados = [
            _liquidado(
                data_vencimento=date(2026, 1, 20),
                data_baixa=date(2026, 1, 30),
                valor_multa=10.0,
                valor_juros=5.0,
            ),
        ]
        perfis = perfil_por_fornecedor(liquidados)
        perfil = perfis["F1"]
        assert perfil.cobra_penalidade is True
        assert perfil.dias_atraso_medio == 10.0
        assert perfil.percentual_penalidade_medio == 1.5
        assert perfil.concede_desconto is False

    def test_fornecedor_sem_padrao_claro(self):
        liquidados = [_liquidado(data_vencimento=date(2026, 1, 20), data_baixa=date(2026, 1, 20))]
        perfil = perfil_por_fornecedor(liquidados)["F1"]
        assert perfil.concede_desconto is False
        assert perfil.cobra_penalidade is False
        assert perfil.dias_antecedencia_medio is None
        assert perfil.percentual_penalidade_medio is None

    def test_titulo_com_valor_original_zero_nao_quebra(self):
        liquidados = [_liquidado(valor_original=0.0, valor_desconto=0.0)]
        perfis = perfil_por_fornecedor(liquidados)
        assert perfis["F1"].concede_desconto is False


class TestRecomendarPagamentos:
    def _perfis_desconto(self):
        return perfil_por_fornecedor(
            [_liquidado(data_vencimento=date(2026, 1, 20), data_baixa=date(2026, 1, 15), valor_desconto=20.0)]
        )

    def _perfis_penalidade(self):
        return perfil_por_fornecedor(
            [_liquidado(data_vencimento=date(2026, 1, 20), data_baixa=date(2026, 1, 30), valor_multa=15.0)]
        )

    def test_fornecedor_com_desconto_recomenda_antecipar(self):
        perfis = self._perfis_desconto()
        recomendacoes = recomendar_pagamentos([_aberto(data_vencimento=date(2026, 3, 20))], perfis)
        assert len(recomendacoes) == 1
        recomendacao = recomendacoes[0]
        assert recomendacao.motivo == "desconto_por_antecipacao"
        assert recomendacao.data_recomendada == date(2026, 3, 15)
        assert recomendacao.economia_estimada == 20.0

    def test_fornecedor_com_penalidade_recomenda_pagar_no_vencimento(self):
        perfis = self._perfis_penalidade()
        recomendacoes = recomendar_pagamentos([_aberto(data_vencimento=date(2026, 3, 20))], perfis)
        assert len(recomendacoes) == 1
        recomendacao = recomendacoes[0]
        assert recomendacao.motivo == "evitar_penalidade_por_atraso"
        assert recomendacao.data_recomendada == date(2026, 3, 20)

    def test_fornecedor_sem_historico_nao_gera_recomendacao(self):
        recomendacoes = recomendar_pagamentos([_aberto(fornecedor_codigo="F99")], {})
        assert recomendacoes == []

    def test_titulo_sem_data_vencimento_nao_gera_recomendacao(self):
        # Achado testando contra o banco fictício local: título aberto de
        # verdade pode ter `data_vencimento` nula — não pode quebrar.
        perfis = self._perfis_desconto()
        recomendacoes = recomendar_pagamentos([_aberto(data_vencimento=None)], perfis)
        assert recomendacoes == []

    def test_ordena_por_maior_economia_primeiro(self):
        perfis = perfil_por_fornecedor(
            [
                _liquidado(
                    fornecedor_codigo="BARATO",
                    data_vencimento=date(2026, 1, 20),
                    data_baixa=date(2026, 1, 15),
                    valor_desconto=5.0,
                ),
                _liquidado(
                    fornecedor_codigo="CARO",
                    data_vencimento=date(2026, 1, 20),
                    data_baixa=date(2026, 1, 15),
                    valor_desconto=100.0,
                ),
            ]
        )
        abertos = [
            _aberto(fornecedor_codigo="BARATO", valor_original=1000.0),
            _aberto(fornecedor_codigo="CARO", valor_original=1000.0),
        ]
        recomendacoes = recomendar_pagamentos(abertos, perfis)
        assert [r.fornecedor_codigo for r in recomendacoes] == ["CARO", "BARATO"]
