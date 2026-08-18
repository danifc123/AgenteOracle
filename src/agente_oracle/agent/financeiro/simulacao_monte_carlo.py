"""Simulação de Cenários Monte Carlo (FP&A) — mesmo espírito de
`projecoes.py`: 100% cálculo estatístico, sem IA, pra número de simulação
nunca depender do Ollama estar no ar.

Em vez de uma única linha de tendência (regressão linear), gera uma
DISTRIBUIÇÃO de cenários futuros por reamostragem (bootstrap) da variação
histórica mês a mês do caixa líquido (recebido - pago): cada simulação
sorteia, com reposição, uma variação real já observada no histórico pra
cada mês futuro, e soma em cadeia a partir do último valor conhecido.

Usa DIFERENÇA absoluta entre meses (não variação percentual): caixa
líquido pode cruzar zero (mês com mais despesa que receita), o que
tornaria variação percentual sem sentido/divisão por zero. Isso também
evita depender de numpy/scipy, que não são dependência do projeto."""

import random
import statistics


def variacoes_mensais(serie: list[float]) -> list[float]:
    """Diferença mês a mês do histórico — a distribuição de onde a
    simulação sorteia. Função pura."""
    return [atual - anterior for anterior, atual in zip(serie, serie[1:])]  # noqa: B905


def simular_cenarios(
    serie_historica: list[float],
    meses_futuros: int,
    num_simulacoes: int,
    semente: int | None = None,
) -> list[list[float]]:
    """Bootstrap: `num_simulacoes` caminhos possíveis pros próximos
    `meses_futuros` meses, cada um sorteando (com reposição) uma variação
    real do histórico por mês e somando em cadeia a partir do último valor
    conhecido. Devolve `[]` com menos de 2 meses de histórico (não dá pra
    calcular variação nenhuma) — mesma guarda de `projetar_tendencia_linear`
    em `projecoes.py`. `semente` só existe pra teste determinístico; em
    produção roda sem semente (aleatório de verdade a cada chamada)."""
    if len(serie_historica) < 2:
        return []

    variacoes = variacoes_mensais(serie_historica)
    gerador = random.Random(semente)
    valor_inicial = serie_historica[-1]

    matriz = []
    for _ in range(num_simulacoes):
        valor = valor_inicial
        caminho = []
        for _ in range(meses_futuros):
            valor += gerador.choice(variacoes)
            caminho.append(valor)
        matriz.append(caminho)
    return matriz


def resumir_percentis(matriz: list[list[float]]) -> list[dict]:
    """Por mês futuro (coluna da matriz), calcula p10/mediana/p90/mínimo/
    máximo entre todas as simulações daquele mês — só ordenação e
    interpolação, sem numpy. Função pura."""
    if not matriz:
        return []

    resumo = []
    for indice_mes in range(len(matriz[0])):
        valores = sorted(caminho[indice_mes] for caminho in matriz)
        resumo.append(
            {
                "p10": _percentil(valores, 10),
                "mediana": statistics.median(valores),
                "p90": _percentil(valores, 90),
                "minimo": valores[0],
                "maximo": valores[-1],
            }
        )
    return resumo


def probabilidade_caixa_negativo(matriz: list[list[float]]) -> float:
    """Fração das simulações em que o caixa líquido fica negativo em ALGUM
    mês futuro (não só no último) — sinal de risco direto pro controller,
    é o "suporte à decisão baseado em dado, não intuição" que a demanda
    original pede. Função pura."""
    if not matriz:
        return 0.0
    caminhos_com_negativo = sum(1 for caminho in matriz if any(valor < 0 for valor in caminho))
    return caminhos_com_negativo / len(matriz)


def _percentil(valores_ordenados: list[float], percentil: int) -> float:
    """Percentil por interpolação linear (mesmo método usado por padrão no
    Excel/numpy) sobre uma lista já ordenada — evita depender de numpy só
    por isso."""
    if len(valores_ordenados) == 1:
        return valores_ordenados[0]
    posicao = (percentil / 100) * (len(valores_ordenados) - 1)
    indice_baixo = int(posicao)
    indice_alto = min(indice_baixo + 1, len(valores_ordenados) - 1)
    fracao = posicao - indice_baixo
    valor_baixo = valores_ordenados[indice_baixo]
    valor_alto = valores_ordenados[indice_alto]
    return valor_baixo + (valor_alto - valor_baixo) * fracao
