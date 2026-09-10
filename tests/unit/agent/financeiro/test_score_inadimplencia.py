from datetime import date

from agente_oracle.agent.financeiro.score_inadimplencia import (
    ComportamentoPagamentoCliente,
    SafraCliente,
    TituloReceberAberto,
    TituloReceberLiquidado,
    calcular_score,
    comportamento_por_cliente,
    safra_relevante_por_cliente,
    titulos_em_risco_por_cliente,
)
from agente_oracle.tools.financeiro.clima_regional import IndicadorClima

_HOJE = date(2026, 6, 1)


def _titulo(
    cliente_codigo: str = "C1",
    cliente_nome: str = "Cliente Um",
    data_vencimento: date = date(2026, 5, 1),
    data_baixa: date = date(2026, 5, 1),
) -> TituloReceberLiquidado:
    return TituloReceberLiquidado(
        cliente_codigo=cliente_codigo,
        cliente_nome=cliente_nome,
        data_vencimento=data_vencimento,
        data_baixa=data_baixa,
    )


def _comportamento(
    percentual_atraso_recente: float = 50.0,
    percentual_atraso_anterior: float = 50.0,
    tendencia: str = "estavel",
) -> ComportamentoPagamentoCliente:
    return ComportamentoPagamentoCliente(
        cliente_codigo="C1",
        cliente_nome="Cliente Um",
        percentual_atraso_recente=percentual_atraso_recente,
        percentual_atraso_anterior=percentual_atraso_anterior,
        dias_atraso_medio=5.0,
        tendencia=tendencia,
    )


def _safra(
    cliente_codigo: str = "C1",
    cultura: str = "SOJA",
    safra_codigo: str = "2025/2026",
    safra_descricao: str = "SAFRA 25/26",
    safra_inicio: date = date(2025, 5, 1),
    safra_fim: date = date(2026, 4, 30),
    data_compra: date = date(2025, 8, 1),
) -> SafraCliente:
    return SafraCliente(
        cliente_codigo=cliente_codigo,
        cultura=cultura,
        safra_codigo=safra_codigo,
        safra_descricao=safra_descricao,
        safra_inicio=safra_inicio,
        safra_fim=safra_fim,
        data_compra=data_compra,
    )


def _titulo_aberto(
    cliente_codigo: str = "C1",
    cliente_nome: str = "Cliente Um",
    numero: str = "1001",
    parcela: str = "01",
    data_vencimento: date = date(2026, 6, 15),
    saldo_aberto: float = 1000.0,
) -> TituloReceberAberto:
    return TituloReceberAberto(
        cliente_codigo=cliente_codigo,
        cliente_nome=cliente_nome,
        numero=numero,
        parcela=parcela,
        data_vencimento=data_vencimento,
        saldo_aberto=saldo_aberto,
    )


class TestComportamentoPorCliente:
    def test_cliente_sem_titulo_em_nenhuma_janela_nao_aparece(self):
        titulos = [_titulo(data_vencimento=date(2024, 1, 1), data_baixa=date(2024, 1, 1))]
        assert comportamento_por_cliente(titulos, _HOJE) == []

    def test_tendencia_piorando(self):
        # janela recente (últimos 90 dias antes de 2026-06-01): tudo atrasado.
        # janela anterior (90 dias antes disso): tudo em dia.
        titulos = [
            _titulo(data_vencimento=date(2026, 5, 10), data_baixa=date(2026, 5, 20)),  # recente, atrasado
            _titulo(data_vencimento=date(2026, 2, 10), data_baixa=date(2026, 2, 10)),  # anterior, em dia
        ]
        comportamentos = comportamento_por_cliente(titulos, _HOJE)
        assert len(comportamentos) == 1
        assert comportamentos[0].tendencia == "piorando"
        assert comportamentos[0].percentual_atraso_recente == 100.0
        assert comportamentos[0].percentual_atraso_anterior == 0.0

    def test_tendencia_melhorando(self):
        titulos = [
            _titulo(data_vencimento=date(2026, 5, 10), data_baixa=date(2026, 5, 10)),  # recente, em dia
            _titulo(data_vencimento=date(2026, 2, 10), data_baixa=date(2026, 2, 20)),  # anterior, atrasado
        ]
        comportamentos = comportamento_por_cliente(titulos, _HOJE)
        assert comportamentos[0].tendencia == "melhorando"

    def test_tendencia_estavel(self):
        titulos = [
            _titulo(data_vencimento=date(2026, 5, 10), data_baixa=date(2026, 5, 20)),
            _titulo(data_vencimento=date(2026, 2, 10), data_baixa=date(2026, 2, 20)),
        ]
        comportamentos = comportamento_por_cliente(titulos, _HOJE)
        assert comportamentos[0].tendencia == "estavel"


class TestSafraRelevantePorCliente:
    def test_safra_que_contem_hoje_e_escolhida(self):
        safras = [_safra(safra_inicio=date(2026, 1, 1), safra_fim=date(2026, 12, 31))]
        relevantes = safra_relevante_por_cliente(safras, _HOJE)
        assert relevantes["C1"].safra_codigo == "2025/2026"

    def test_safra_que_ainda_nao_comecou_e_ignorada(self):
        safras = [_safra(safra_inicio=date(2026, 7, 1), safra_fim=date(2027, 6, 30))]
        assert safra_relevante_por_cliente(safras, _HOJE) == {}

    def test_safra_encerrada_ha_muito_tempo_e_ignorada(self):
        safras = [_safra(safra_inicio=date(2024, 1, 1), safra_fim=date(2024, 12, 31))]
        assert safra_relevante_por_cliente(safras, _HOJE) == {}

    def test_safra_encerrada_recentemente_ainda_conta(self):
        # _HOJE = 2026-06-01, safra terminou 2026-04-30 -> 32 dias atrás,
        # dentro da graça de 90 dias (a colheita recém-vendida ainda
        # explica um atraso agora).
        safras = [_safra(safra_inicio=date(2025, 10, 1), safra_fim=date(2026, 4, 30))]
        relevantes = safra_relevante_por_cliente(safras, _HOJE)
        assert relevantes["C1"].safra_codigo == "2025/2026"

    def test_safra_encerrada_fora_da_graca_e_ignorada(self):
        # Terminou 120 dias atrás — fora dos 90 dias de graça.
        safras = [_safra(safra_inicio=date(2025, 6, 1), safra_fim=date(2026, 2, 1))]
        assert safra_relevante_por_cliente(safras, _HOJE) == {}

    def test_duas_candidatas_prioriza_a_em_andamento_sobre_a_encerrada(self):
        safras = [
            _safra(
                cultura="MILHO",
                safra_inicio=date(2025, 10, 1),
                safra_fim=date(2026, 4, 30),  # encerrada há 32 dias, dentro da graça
                data_compra=date(2025, 10, 1),
            ),
            _safra(
                cultura="SOJA",
                safra_inicio=date(2026, 1, 1),
                safra_fim=date(2026, 12, 31),  # em andamento agora
                data_compra=date(2026, 1, 1),
            ),
        ]
        relevantes = safra_relevante_por_cliente(safras, _HOJE)
        assert relevantes["C1"].cultura == "SOJA"

    def test_duas_safras_ativas_escolhe_compra_mais_recente(self):
        safras = [
            _safra(
                cultura="SOJA",
                safra_inicio=date(2026, 1, 1),
                safra_fim=date(2026, 12, 31),
                data_compra=date(2026, 1, 1),
            ),
            _safra(
                cultura="MILHO",
                safra_inicio=date(2026, 1, 1),
                safra_fim=date(2026, 12, 31),
                data_compra=date(2026, 3, 1),
            ),
        ]
        relevantes = safra_relevante_por_cliente(safras, _HOJE)
        assert relevantes["C1"].cultura == "MILHO"

    def test_duas_candidatas_encerradas_escolhe_a_mais_recente(self):
        safras = [
            _safra(
                cultura="MILHO",
                safra_inicio=date(2025, 1, 1),
                safra_fim=date(2026, 1, 1),  # encerrada há 151 dias, fora da graça
                data_compra=date(2025, 1, 1),
            ),
            _safra(
                cultura="SOJA",
                safra_inicio=date(2025, 10, 1),
                safra_fim=date(2026, 4, 30),  # encerrada há 32 dias, dentro da graça
                data_compra=date(2025, 10, 1),
            ),
        ]
        relevantes = safra_relevante_por_cliente(safras, _HOJE)
        assert relevantes["C1"].cultura == "SOJA"

    def test_cliente_sem_safra_nenhuma_nao_aparece_no_dict(self):
        assert safra_relevante_por_cliente([], _HOJE) == {}


class TestTitulosEmRiscoPorCliente:
    def test_titulo_dentro_da_janela_de_cliente_com_score_aparece(self):
        score = calcular_score(_comportamento(percentual_atraso_recente=50.0), None, None)
        titulo = _titulo_aberto(data_vencimento=date(2026, 6, 20))
        resultado = titulos_em_risco_por_cliente([titulo], {"C1": score}, _HOJE, horizonte_dias=60)
        assert len(resultado) == 1
        assert resultado[0].dias_ate_vencimento == 19
        assert resultado[0].score is score

    def test_titulo_fora_da_janela_de_60_dias_e_excluido(self):
        score = calcular_score(_comportamento(percentual_atraso_recente=50.0), None, None)
        titulo = _titulo_aberto(data_vencimento=date(2026, 9, 1))  # 92 dias à frente
        resultado = titulos_em_risco_por_cliente([titulo], {"C1": score}, _HOJE, horizonte_dias=60)
        assert resultado == []

    def test_titulo_ja_vencido_e_excluido(self):
        score = calcular_score(_comportamento(percentual_atraso_recente=50.0), None, None)
        titulo = _titulo_aberto(data_vencimento=date(2026, 5, 1))  # antes de hoje
        resultado = titulos_em_risco_por_cliente([titulo], {"C1": score}, _HOJE, horizonte_dias=60)
        assert resultado == []

    def test_titulo_de_cliente_sem_score_e_excluido(self):
        titulo = _titulo_aberto(cliente_codigo="C2", data_vencimento=date(2026, 6, 20))
        resultado = titulos_em_risco_por_cliente([titulo], {}, _HOJE, horizonte_dias=60)
        assert resultado == []

    def test_ordenado_por_dias_ate_vencimento_crescente(self):
        score = calcular_score(_comportamento(percentual_atraso_recente=50.0), None, None)
        titulos = [
            _titulo_aberto(numero="2", data_vencimento=date(2026, 7, 1)),
            _titulo_aberto(numero="1", data_vencimento=date(2026, 6, 10)),
        ]
        resultado = titulos_em_risco_por_cliente(titulos, {"C1": score}, _HOJE, horizonte_dias=60)
        assert [titulo.numero for titulo in resultado] == ["1", "2"]


class TestCalcularScore:
    def test_pontuacao_so_de_comportamento_sem_clima(self):
        score = calcular_score(
            _comportamento(percentual_atraso_recente=50.0, tendencia="estavel"), None, _safra()
        )
        assert score.score == 35  # 50% de 70 pontos
        assert "clima regional indisponível no momento" in score.fatores[-1]

    def test_bonus_de_tendencia_piorando(self):
        score = calcular_score(
            _comportamento(percentual_atraso_recente=50.0, tendencia="piorando"), None, _safra()
        )
        assert score.score == 50  # 35 + 15 de bônus
        assert any("piorando" in fator for fator in score.fatores)

    def test_score_nunca_ultrapassa_100(self):
        score = calcular_score(
            _comportamento(percentual_atraso_recente=100.0, tendencia="piorando"), None, _safra()
        )
        assert score.score <= 100

    def test_clima_seca_soma_pontos_com_safra_ativa(self):
        clima = IndicadorClima("Cuiaba", "MT", -80.0, "seca")
        score = calcular_score(
            _comportamento(percentual_atraso_recente=0.0, tendencia="estavel"), clima, _safra()
        )
        assert score.score == 30
        assert any("seca" in fator for fator in score.fatores)

    def test_clima_normal_nao_soma_pontos(self):
        clima = IndicadorClima("Cuiaba", "MT", 5.0, "normal")
        score = calcular_score(
            _comportamento(percentual_atraso_recente=0.0, tendencia="estavel"), clima, _safra()
        )
        assert score.score == 0

    def test_sem_safra_ativa_clima_nao_soma_pontos_mesmo_com_seca(self):
        # Achado central da opção B: clima só é sinal enquanto a safra do
        # cliente está na janela crítica — sem safra ativa, mesmo uma seca
        # de verdade na região não conta nada no score.
        clima = IndicadorClima("Cuiaba", "MT", -80.0, "seca")
        score = calcular_score(
            _comportamento(percentual_atraso_recente=0.0, tendencia="estavel"), clima, None
        )
        assert score.score == 0
        assert "sem safra relevante" in score.fatores[-1]
