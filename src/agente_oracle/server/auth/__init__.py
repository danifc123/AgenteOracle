from agente_oracle.server.auth import cores_ambiente, rotas


def registrar(mcp) -> None:
    rotas.registrar(mcp)
    cores_ambiente.registrar(mcp)
