"""Score de Inadimplência — comportamento de pagamento + clima regional.

IMPORTANTE, pra não prometer mais do que existe: isto é um indicador
composto por REGRA clara (comportamento + clima), não um modelo de
machine learning treinado com resultado histórico rotulado — não existe
pipeline de treino/validação neste projeto, e criar um de verdade seria
uma frente bem maior, separada desta. Cada fator do score vira uma frase
legível em `fatores`, nunca uma caixa preta.

Comportamento de pagamento é 100% cálculo sobre títulos já liquidados de
`vwia_titulos_receber` (sem IA). Clima regional vem de `clima_regional.py`
(Open-Meteo, opcional — `None`/`indisponivel` nunca derruba o score)."""

from dataclasses import dataclass
from datetime import date, timedelta

from agente_oracle.tools.financeiro.clima_regional import IndicadorClima

_DIAS_JANELA_RECENTE = 90
_DIAS_JANELA_ANTERIOR = 90  # os 90 dias imediatamente antes da janela recente
_LIMIAR_TENDENCIA_PERCENTUAL = 10.0

_PONTOS_MAXIMO_COMPORTAMENTO = 70
_PONTOS_MAXIMO_CLIMA = 30
_BONUS_TENDENCIA_PIORANDO = 15

# Quantos dias depois do fim de uma safra sua colheita ainda "explica" um
# atraso de pagamento — a receita de uma safra recém-encerrada é o que
# financia os títulos vencendo agora, então o clima dela continua
# relevante por um tempo depois de `safra_fim` (ver `safra_relevante_por_cliente`).
_DIAS_GRACA_SAFRA_ENCERRADA = 90


@dataclass(frozen=True)
class TituloReceberLiquidado:
    cliente_codigo: str
    cliente_nome: str
    data_vencimento: date
    data_baixa: date


@dataclass(frozen=True)
class SafraCliente:
    cliente_codigo: str
    cultura: str
    safra_codigo: str
    safra_descricao: str
    safra_inicio: date
    safra_fim: date
    data_compra: date


@dataclass(frozen=True)
class ComportamentoPagamentoCliente:
    cliente_codigo: str
    cliente_nome: str
    percentual_atraso_recente: float
    percentual_atraso_anterior: float
    dias_atraso_medio: float
    tendencia: str  # "piorando" | "estavel" | "melhorando"


@dataclass(frozen=True)
class ScoreInadimplencia:
    cliente_codigo: str
    cliente_nome: str
    score: int
    comportamento: ComportamentoPagamentoCliente
    clima: IndicadorClima | None
    safra_ativa: SafraCliente | None
    fatores: tuple[str, ...]


@dataclass(frozen=True)
class TituloReceberAberto:
    cliente_codigo: str
    cliente_nome: str
    numero: str
    parcela: str
    data_vencimento: date
    saldo_aberto: float


@dataclass(frozen=True)
class TituloEmRisco:
    cliente_codigo: str
    cliente_nome: str
    numero: str
    parcela: str
    data_vencimento: date
    saldo_aberto: float
    dias_ate_vencimento: int
    score: ScoreInadimplencia


def calcular_score(
    comportamento: ComportamentoPagamentoCliente,
    clima: IndicadorClima | None,
    safra_ativa: SafraCliente | None,
) -> ScoreInadimplencia:
    """Pontuação 0–100 (maior = mais risco): até `_PONTOS_MAXIMO_COMPORTAMENTO`
    pontos vêm do percentual de atraso recente (mais bônus se a tendência
    for piorando), até `_PONTOS_MAXIMO_CLIMA` pontos vêm de anomalia
    climática extrema (seca ou excesso de chuva) na região do cliente —
    mas SÓ quando `safra_ativa` não é `None`: clima só é sinal de risco
    de inadimplência enquanto está afetando a safra que vai gerar (ou
    gerou, se recém-encerrada) a receita que paga o título
    (`safra_relevante_por_cliente`); fora dessa janela, clima é ruído e
    não conta nada no score, mesmo que esteja anômalo de verdade na
    região."""
    fatores = [
        f"{comportamento.percentual_atraso_recente:.0f}% dos títulos pagos com atraso nos últimos 90 dias"
    ]

    pontos_comportamento = min(
        float(_PONTOS_MAXIMO_COMPORTAMENTO),
        comportamento.percentual_atraso_recente / 100 * _PONTOS_MAXIMO_COMPORTAMENTO,
    )
    if comportamento.tendencia == "piorando":
        pontos_comportamento = min(
            float(_PONTOS_MAXIMO_COMPORTAMENTO), pontos_comportamento + _BONUS_TENDENCIA_PIORANDO
        )
        fatores.append("comportamento de pagamento piorando em relação ao período anterior")
    elif comportamento.tendencia == "melhorando":
        fatores.append("comportamento de pagamento melhorando em relação ao período anterior")

    pontos_clima = 0.0
    if safra_ativa is None:
        fatores.append("sem safra relevante no momento — clima não considerado no score")
    elif clima is not None and clima.classificacao in ("seca", "excesso_chuva"):
        pontos_clima = float(_PONTOS_MAXIMO_CLIMA)
        rotulo_clima = "seca" if clima.classificacao == "seca" else "excesso de chuva"
        fatores.append(
            f"{rotulo_clima} na região na safra de {safra_ativa.cultura} ({safra_ativa.safra_descricao})"
        )
    elif clima is None or clima.classificacao == "indisponivel":
        fatores.append("clima regional indisponível no momento")

    return ScoreInadimplencia(
        cliente_codigo=comportamento.cliente_codigo,
        cliente_nome=comportamento.cliente_nome,
        score=round(pontos_comportamento + pontos_clima),
        comportamento=comportamento,
        clima=clima,
        safra_ativa=safra_ativa,
        fatores=tuple(fatores),
    )


def comportamento_por_cliente(
    liquidados: list[TituloReceberLiquidado], hoje: date
) -> list[ComportamentoPagamentoCliente]:
    """Compara os últimos `_DIAS_JANELA_RECENTE` dias contra os
    `_DIAS_JANELA_ANTERIOR` dias imediatamente antes disso, por cliente —
    cliente sem título liquidado em nenhuma das duas janelas não aparece
    no resultado (não tem comportamento recente pra avaliar)."""
    corte_recente = hoje - timedelta(days=_DIAS_JANELA_RECENTE)
    corte_anterior = corte_recente - timedelta(days=_DIAS_JANELA_ANTERIOR)

    por_cliente: dict[str, list[TituloReceberLiquidado]] = {}
    for titulo in liquidados:
        por_cliente.setdefault(titulo.cliente_codigo, []).append(titulo)

    resultado = []
    for cliente_codigo, titulos in por_cliente.items():
        recentes = [titulo for titulo in titulos if titulo.data_baixa >= corte_recente]
        anteriores = [titulo for titulo in titulos if corte_anterior <= titulo.data_baixa < corte_recente]
        if not recentes and not anteriores:
            continue

        percentual_recente = _percentual_atraso(recentes)
        percentual_anterior = _percentual_atraso(anteriores)
        atrasados_recentes = [titulo for titulo in recentes if titulo.data_baixa > titulo.data_vencimento]
        dias_atraso_medio = (
            sum((titulo.data_baixa - titulo.data_vencimento).days for titulo in atrasados_recentes)
            / len(atrasados_recentes)
            if atrasados_recentes
            else 0.0
        )

        resultado.append(
            ComportamentoPagamentoCliente(
                cliente_codigo=cliente_codigo,
                cliente_nome=titulos[0].cliente_nome,
                percentual_atraso_recente=percentual_recente,
                percentual_atraso_anterior=percentual_anterior,
                dias_atraso_medio=round(dias_atraso_medio, 1),
                tendencia=_tendencia(percentual_recente, percentual_anterior),
            )
        )
    return resultado


def _percentual_atraso(titulos: list[TituloReceberLiquidado]) -> float:
    if not titulos:
        return 0.0
    atrasados = sum(1 for titulo in titulos if titulo.data_baixa > titulo.data_vencimento)
    return round(atrasados / len(titulos) * 100, 1)


def _tendencia(percentual_recente: float, percentual_anterior: float) -> str:
    diferenca = percentual_recente - percentual_anterior
    if diferenca >= _LIMIAR_TENDENCIA_PERCENTUAL:
        return "piorando"
    if diferenca <= -_LIMIAR_TENDENCIA_PERCENTUAL:
        return "melhorando"
    return "estavel"


def safra_relevante_por_cliente(safras: list[SafraCliente], hoje: date) -> dict[str, SafraCliente]:
    """Por cliente, entre as compras cuja safra JÁ COMEÇOU (`safra_inicio
    <= hoje` — não dá pra avaliar clima de uma safra que ainda nem
    começou) e que está em andamento (`safra_fim >= hoje`) OU terminou há
    no máximo `_DIAS_GRACA_SAFRA_ENCERRADA` dias, escolhe uma: prioriza a
    que está em andamento agora (a de `data_compra` mais recente, entre
    essas); sem nenhuma em andamento, a que terminou mais recentemente
    (`safra_fim` maior). A colheita que acabou de terminar é o que
    financia os títulos vencendo agora, então o clima dela ainda importa
    — só considerar a safra "em andamento agora" perderia justamente o
    caso mais comum de explicar um atraso: colheita ruim recente. Cliente
    sem nenhuma safra candidata simplesmente não entra no dict — o clima
    não conta pra ele (ver `calcular_score`). Cliente com mais de uma
    cultura candidata ao mesmo tempo fica só com a melhor candidata pelo
    critério acima — simplificação de v1."""
    candidatas_por_cliente: dict[str, list[SafraCliente]] = {}
    for safra in safras:
        if safra.safra_inicio > hoje:
            continue
        em_andamento = safra.safra_fim >= hoje
        dentro_da_graca = (hoje - safra.safra_fim).days <= _DIAS_GRACA_SAFRA_ENCERRADA
        if not (em_andamento or dentro_da_graca):
            continue
        candidatas_por_cliente.setdefault(safra.cliente_codigo, []).append(safra)

    resultado: dict[str, SafraCliente] = {}
    for cliente_codigo, candidatas in candidatas_por_cliente.items():
        em_andamento = [safra for safra in candidatas if safra.safra_fim >= hoje]
        if em_andamento:
            resultado[cliente_codigo] = max(em_andamento, key=lambda safra: safra.data_compra)
        else:
            resultado[cliente_codigo] = max(candidatas, key=lambda safra: safra.safra_fim)
    return resultado


def titulos_em_risco_por_cliente(
    abertos: list[TituloReceberAberto],
    scores_por_cliente: dict[str, ScoreInadimplencia],
    hoje: date,
    horizonte_dias: int = 60,
) -> list[TituloEmRisco]:
    """Liga cada título em aberto que vence dentro de `horizonte_dias` ao
    score de risco que o cliente responsável já carrega — não inventa um
    número novo, só mostra QUAIS títulos concretos estão em jogo pro
    risco que o cliente já tem. Título de cliente sem nenhum indício de
    risco (fora de `scores_por_cliente` — ver `_apenas_com_risco` no
    server) não entra. Ordenado por `dias_ate_vencimento` crescente, o
    mais urgente primeiro."""
    fim_janela = hoje + timedelta(days=horizonte_dias)
    resultado = []
    for titulo in abertos:
        score = scores_por_cliente.get(titulo.cliente_codigo)
        if score is None or not (hoje <= titulo.data_vencimento <= fim_janela):
            continue
        resultado.append(
            TituloEmRisco(
                cliente_codigo=titulo.cliente_codigo,
                cliente_nome=titulo.cliente_nome,
                numero=titulo.numero,
                parcela=titulo.parcela,
                data_vencimento=titulo.data_vencimento,
                saldo_aberto=titulo.saldo_aberto,
                dias_ate_vencimento=(titulo.data_vencimento - hoje).days,
                score=score,
            )
        )
    resultado.sort(key=lambda item: item.dias_ate_vencimento)
    return resultado
