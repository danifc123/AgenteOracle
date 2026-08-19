from datetime import date

from agente_oracle.agent.financeiro.clima_regional import IndicadorClima
from agente_oracle.agent.financeiro.score_inadimplencia import (
    ComportamentoPagamentoCliente,
    SafraCliente,
    TituloReceberLiquidado,
    calcular_score,
    comportamento_por_cliente,
    safra_ativa_por_cliente,
)

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


class TestSafraAtivaPorCliente:
    def test_safra_que_contem_hoje_e_escolhida(self):
        safras = [_safra(safra_inicio=date(2026, 1, 1), safra_fim=date(2026, 12, 31))]
        ativas = safra_ativa_por_cliente(safras, _HOJE)
        assert ativas["C1"].safra_codigo == "2025/2026"

    def test_safra_fora_da_janela_e_ignorada(self):
        safras = [_safra(safra_inicio=date(2024, 1, 1), safra_fim=date(2024, 12, 31))]
        assert safra_ativa_por_cliente(safras, _HOJE) == {}

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
        ativas = safra_ativa_por_cliente(safras, _HOJE)
        assert ativas["C1"].cultura == "MILHO"

    def test_cliente_sem_safra_nenhuma_nao_aparece_no_dict(self):
        assert safra_ativa_por_cliente([], _HOJE) == {}


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
        assert "sem safra ativa" in score.fatores[-1]
