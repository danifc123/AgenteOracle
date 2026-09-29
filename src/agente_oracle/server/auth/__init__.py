from agente_oracle.server.auth import cores_ambiente, relatorios_fixados, rotas


def registrar(mcp) -> None:
    rotas.registrar(mcp)
    cores_ambiente.registrar(mcp)
    relatorios_fixados.registrar(mcp)
