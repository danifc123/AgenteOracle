from agente_oracle.server.ti import chamados, seguranca


def registrar(mcp) -> None:
    chamados.registrar(mcp)
    seguranca.registrar(mcp)
