from agente_oracle.server.financeiro import (
    categoria_cores,
    classificacao_contabil,
    despesas_suspeitas,
    historico,
    ia,
    layouts,
    previsao,
    relatorios,
    score_inadimplencia,
    simulacao_monte_carlo,
)


def registrar(mcp) -> None:
    relatorios.registrar(mcp)
    historico.registrar(mcp)
    layouts.registrar(mcp)
    categoria_cores.registrar(mcp)
    ia.registrar(mcp)
    previsao.registrar(mcp)
    despesas_suspeitas.registrar(mcp)
    simulacao_monte_carlo.registrar(mcp)
    classificacao_contabil.registrar(mcp)
    score_inadimplencia.registrar(mcp)
