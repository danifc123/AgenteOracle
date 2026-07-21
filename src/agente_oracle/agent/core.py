"""Utilitários genéricos, reutilizáveis por qualquer módulo de IA (Financeiro,
e futuramente RH, Compras etc.) — nada aqui é específico de um módulo. A
lógica de decisão/schema/regras de cada módulo fica no próprio módulo (ver
`agent/financeiro/financeiro.py` como referência de implementação)."""

from mcp.types import CallToolResult


def mcp_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/mcp"


def conteudo_do_resultado(resultado: CallToolResult) -> str:
    """Converte o resultado de uma chamada MCP (`session.call_tool`) no texto
    puro que veio nele — usado por qualquer módulo que precise interpretar o
    resultado de uma tool chamada via MCP."""
    partes = [bloco.text for bloco in resultado.content if getattr(bloco, "text", None)]
    return "\n".join(partes) if partes else str(resultado)
