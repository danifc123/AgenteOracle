"""Lógica pura das telas de Previsão (Vendas e Fluxo de Caixa) do Financeiro:
regressão linear simples pra projetar vendas futuras. Sem I/O de banco — as
queries que alimentam essas funções ficam em `server/financeiro/previsao.py`.
100% cálculo estatístico, sem IA — decisão deliberada pra número de previsão
nunca depender de o Ollama estar no ar (ver `server/financeiro/previsao.py`)."""


def projetar_tendencia_linear(serie: list[float], meses_futuros: int) -> list[float]:
    """Projeta os próximos `meses_futuros` valores por regressão linear
    (mínimos quadrados) sobre `serie`, tratando cada posição como um mês
    sequencial (0, 1, 2, ...). Com menos de 2 pontos não há tendência
    possível de calcular, devolve lista vazia."""
    n = len(serie)
    if n < 2:
        return []

    soma_x = sum(range(n))
    soma_y = sum(serie)
    soma_xy = sum(indice * valor for indice, valor in enumerate(serie))
    soma_x2 = sum(indice * indice for indice in range(n))

    inclinacao = (n * soma_xy - soma_x * soma_y) / (n * soma_x2 - soma_x * soma_x)
    intercepto = (soma_y - inclinacao * soma_x) / n

    return [round(inclinacao * (n + passo) + intercepto, 2) for passo in range(meses_futuros)]


def proximos_meses(mes_referencia: str, quantidade: int) -> list[str]:
    """Gera os `quantidade` rótulos "YYYY-MM" seguintes a `mes_referencia`
    (também "YYYY-MM"), tratando virada de ano."""
    ano, mes = (int(parte) for parte in mes_referencia.split("-"))

    rotulos = []
    for _ in range(quantidade):
        mes += 1
        if mes > 12:
            mes = 1
            ano += 1
        rotulos.append(f"{ano:04d}-{mes:02d}")
    return rotulos
