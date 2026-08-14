"""Utilitários genéricos, reutilizáveis por qualquer módulo de IA (Financeiro,
e futuramente RH, Compras etc.) — nada aqui é específico de um módulo. A
lógica de decisão/schema/regras de cada módulo fica no próprio módulo (ver
`agent/financeiro/financeiro.py` como referência de implementação)."""

import json

from mcp.types import CallToolResult

# Opções padrão de chamada ao Ollama, usadas por todo módulo de IA
# (Financeiro, RH, TI, Auditoria) — 16384 dá espaço de sobra pro maior prompt
# que qualquer um desses módulos monta hoje, consumindo uma fração da
# memória que o valor default do Ollama reservaria.
OPCOES_OLLAMA_PADRAO = {"num_ctx": 16384}


def conteudo_do_resultado(resultado: CallToolResult) -> str:
    """Converte o resultado de uma chamada MCP (`session.call_tool`) no texto
    puro que veio nele — usado por qualquer módulo que precise interpretar o
    resultado de uma tool chamada via MCP."""
    partes = [bloco.text for bloco in resultado.content if getattr(bloco, "text", None)]
    return "\n".join(partes) if partes else str(resultado)


def mcp_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/mcp"


def resposta_json_como_dict(conteudo: str | None) -> dict:
    """Interpreta o conteúdo de uma resposta de chat do Ollama (JSON forçado
    via `format=`) como dict — devolve `{}` se `conteudo` for None/vazio, não
    for JSON válido, ou for JSON válido mas não-objeto (`null`, `[]`,
    `false`). Nunca deixa quem chama arriscar `AttributeError` de `.get()`
    num tipo errado — mesma classe de bug já corrigida à mão em vários
    módulos de IA antes desta função existir."""
    if not conteudo:
        return {}
    try:
        corpo = json.loads(conteudo)
    except json.JSONDecodeError:
        return {}
    return corpo if isinstance(corpo, dict) else {}