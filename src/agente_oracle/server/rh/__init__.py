from agente_oracle.server.rh import busca, candidatos


def registrar(mcp) -> None:
    candidatos.registrar(mcp)
    busca.registrar(mcp)
