from agente_oracle.server.financeiro import (
    categoria_cores,
    despesas_suspeitas,
    historico,
    ia,
    layouts,
    previsao,
    relatorios,
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
