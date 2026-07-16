from agente_oracle.server.financeiro import historico, ia, relatorios


def registrar(mcp) -> None:
    relatorios.registrar(mcp)
    historico.registrar(mcp)
    ia.registrar(mcp)
