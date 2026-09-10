from agente_oracle.server.ti import chamados, configuracoes, seguranca, webhook_glpi


def registrar(mcp) -> None:
    chamados.registrar(mcp)
    configuracoes.registrar(mcp)
    seguranca.registrar(mcp)
    webhook_glpi.registrar(mcp)
