from agente_oracle.server.ti import (
    chamados,
    configuracoes,
    provedores_llm,
    seguranca,
    tecnicos_glpi,
    uso_ia,
    webhook_glpi,
)


def registrar(mcp) -> None:
    chamados.registrar(mcp)
    configuracoes.registrar(mcp)
    provedores_llm.registrar(mcp)
    seguranca.registrar(mcp)
    tecnicos_glpi.registrar(mcp)
    uso_ia.registrar(mcp)
    webhook_glpi.registrar(mcp)
