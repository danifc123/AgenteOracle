from agente_oracle.server.financeiro import filiais, historico, ia, relatorios


def registrar(mcp) -> None:
    filiais.registrar(mcp)
    relatorios.registrar(mcp)
    historico.registrar(mcp)
    ia.registrar(mcp)
