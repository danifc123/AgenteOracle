from agente_oracle.server.rh import candidatos, vagas


def registrar(mcp) -> None:
    vagas.registrar(mcp)
    candidatos.registrar(mcp)
