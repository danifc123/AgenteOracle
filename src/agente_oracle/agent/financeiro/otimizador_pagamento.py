"""Otimizador de Fluxo de Caixa Preditivo — mesmo espírito de
`projecoes.py`/`despesas_suspeitas.py`: número não pode depender do
Ollama, então isto é 100% cálculo sobre o histórico real de pagamento,
sem IA.

Ideia: pra cada fornecedor, o histórico de títulos já pagos (`data_baixa`
preenchida) mostra se ele costuma conceder desconto por pagamento
antecipado, cobrar multa/juros por atraso, ou nenhum dos dois — e a
recomendação pro título ainda em aberto usa esse padrão real do próprio
fornecedor, nunca um valor genérico. Fornecedor sem padrão histórico
claro (nenhum título liquidado com desconto ou penalidade) não recebe
recomendação nenhuma — mais honesto que forçar um palpite sem base."""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class TituloPagarLiquidado:
    fornecedor_codigo: str
    fornecedor_nome: str
    valor_original: float
    data_vencimento: date
    data_baixa: date
    valor_desconto: float
    valor_multa: float
    valor_juros: float


@dataclass(frozen=True)
class TituloPagarAberto:
    fornecedor_codigo: str
    fornecedor_nome: str
    prefixo: str
    numero: str
    parcela: str
    valor_original: float
    # `None` acontece de verdade (achado testando contra o banco fictício
    # local) — título aberto cuja `data_vencimento` ainda não foi
    # preenchida. Sem data de vencimento não tem como recomendar quando
    # pagar, então esse título é pulado em `recomendar_pagamentos`.
    data_vencimento: date | None


@dataclass(frozen=True)
class PerfilPagamentoFornecedor:
    fornecedor_codigo: str
    concede_desconto: bool
    dias_antecedencia_medio: float | None
    percentual_desconto_medio: float | None
    cobra_penalidade: bool
    dias_atraso_medio: float | None
    percentual_penalidade_medio: float | None


@dataclass(frozen=True)
class RecomendacaoPagamento:
    fornecedor_codigo: str
    fornecedor_nome: str
    documento: str
    valor_original: float
    data_vencimento: date
    data_recomendada: date
    economia_estimada: float
    motivo: str  # "desconto_por_antecipacao" | "evitar_penalidade_por_atraso"


def _media(valores: list[float]) -> float | None:
    return sum(valores) / len(valores) if valores else None


def perfil_por_fornecedor(liquidados: list[TituloPagarLiquidado]) -> dict[str, PerfilPagamentoFornecedor]:
    """Agrupa o histórico de títulos já pagos por fornecedor e resume o
    padrão de desconto/penalidade de cada um. Só considera título com
    `valor_original > 0` nos percentuais (evita divisão por zero e título
    de estorno)."""
    por_fornecedor: dict[str, list[TituloPagarLiquidado]] = {}
    for titulo in liquidados:
        por_fornecedor.setdefault(titulo.fornecedor_codigo, []).append(titulo)

    perfis: dict[str, PerfilPagamentoFornecedor] = {}
    for fornecedor_codigo, titulos in por_fornecedor.items():
        com_desconto = [t for t in titulos if t.valor_original > 0 and t.valor_desconto > 0]
        com_penalidade = [t for t in titulos if t.valor_original > 0 and (t.valor_multa + t.valor_juros) > 0]

        dias_antecedencia_medio = _media([(t.data_vencimento - t.data_baixa).days for t in com_desconto])
        percentual_desconto_medio = _media([t.valor_desconto / t.valor_original * 100 for t in com_desconto])

        dias_atraso_medio = _media([(t.data_baixa - t.data_vencimento).days for t in com_penalidade])
        percentual_penalidade_medio = _media(
            [(t.valor_multa + t.valor_juros) / t.valor_original * 100 for t in com_penalidade]
        )

        perfis[fornecedor_codigo] = PerfilPagamentoFornecedor(
            fornecedor_codigo=fornecedor_codigo,
            concede_desconto=bool(dias_antecedencia_medio and dias_antecedencia_medio >= 1),
            dias_antecedencia_medio=dias_antecedencia_medio,
            percentual_desconto_medio=percentual_desconto_medio,
            cobra_penalidade=bool(dias_atraso_medio and dias_atraso_medio > 0),
            dias_atraso_medio=dias_atraso_medio,
            percentual_penalidade_medio=percentual_penalidade_medio,
        )
    return perfis


def recomendar_pagamentos(
    abertos: list[TituloPagarAberto], perfis: dict[str, PerfilPagamentoFornecedor]
) -> list[RecomendacaoPagamento]:
    """Pra cada título aberto, usa o perfil do próprio fornecedor: se ele
    costuma dar desconto por antecipação, recomenda a mesma antecedência
    média; senão, se costuma cobrar multa/juros por atraso, recomenda
    pagar até o vencimento. Fornecedor sem perfil (nunca apareceu no
    histórico liquidado), sem padrão claro, ou título sem `data_vencimento`
    preenchida não gera recomendação — ordenado pela maior economia
    estimada primeiro."""
    recomendacoes = []
    for titulo in abertos:
        if titulo.data_vencimento is None:
            continue
        perfil = perfis.get(titulo.fornecedor_codigo)
        if perfil is None:
            continue

        documento = f"{titulo.prefixo}-{titulo.numero}-{titulo.parcela}"

        if perfil.concede_desconto:
            dias = round(perfil.dias_antecedencia_medio)  # type: ignore[arg-type]
            recomendacoes.append(
                RecomendacaoPagamento(
                    fornecedor_codigo=titulo.fornecedor_codigo,
                    fornecedor_nome=titulo.fornecedor_nome,
                    documento=documento,
                    valor_original=titulo.valor_original,
                    data_vencimento=titulo.data_vencimento,
                    data_recomendada=titulo.data_vencimento - timedelta(days=dias),
                    economia_estimada=round(
                        titulo.valor_original * perfil.percentual_desconto_medio / 100,  # type: ignore[operator]
                        2,
                    ),
                    motivo="desconto_por_antecipacao",
                )
            )
        elif perfil.cobra_penalidade:
            recomendacoes.append(
                RecomendacaoPagamento(
                    fornecedor_codigo=titulo.fornecedor_codigo,
                    fornecedor_nome=titulo.fornecedor_nome,
                    documento=documento,
                    valor_original=titulo.valor_original,
                    data_vencimento=titulo.data_vencimento,
                    data_recomendada=titulo.data_vencimento,
                    economia_estimada=round(
                        titulo.valor_original * perfil.percentual_penalidade_medio / 100,  # type: ignore[operator]
                        2,
                    ),
                    motivo="evitar_penalidade_por_atraso",
                )
            )

    recomendacoes.sort(key=lambda recomendacao: recomendacao.economia_estimada, reverse=True)
    return recomendacoes
