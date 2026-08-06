from agente_oracle.server.financeiro import categoria_cores, historico, ia, layouts, previsao, relatorios


def registrar(mcp) -> None:
    relatorios.registrar(mcp)
    historico.registrar(mcp)
    layouts.registrar(mcp)
    categoria_cores.registrar(mcp)
    ia.registrar(mcp)
    previsao.registrar(mcp)
