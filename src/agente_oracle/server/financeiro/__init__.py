from agente_oracle.server.financeiro import historico, ia, layouts, relatorios


def registrar(mcp) -> None:
    relatorios.registrar(mcp)
    historico.registrar(mcp)
    layouts.registrar(mcp)
    ia.registrar(mcp)
