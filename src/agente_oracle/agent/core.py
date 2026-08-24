"""Utilitários genéricos, reutilizáveis por qualquer módulo de IA (Financeiro,
e futuramente RH, Compras etc.) — nada aqui é específico de um módulo. A
lógica de decisão/schema/regras de cada módulo fica no próprio módulo (ver
`agent/financeiro/financeiro.py` como referência de implementação)."""

import json
import logging

from mcp.types import CallToolResult

_logger = logging.getLogger(__name__)

# Opções padrão de chamada ao Ollama, usadas por todo módulo de IA
# (Financeiro, RH, TI, Auditoria) — 16384 dá espaço de sobra pro maior prompt
# que qualquer um desses módulos monta hoje, consumindo uma fração da
# memória que o valor default do Ollama reservaria.
OPCOES_OLLAMA_PADRAO = {"num_ctx": 16384}

# Usados por `sanitizar_historico` — mesmo limite serve pra validar o
# tamanho da mensagem que o usuário acabou de digitar (ver call site em
# `server/financeiro/ia.py`).
PAPEIS_HISTORICO_PERMITIDOS = {"user", "assistant"}
MAX_CARACTERES_CONTEUDO = 4000
MAX_HISTORICO_ENTRADAS = 20


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


def sanitizar_historico(historico_bruto: object) -> list[dict[str, str]]:
    """Valida o histórico de mensagens que o cliente manda de volta no chat
    antes dele entrar no contexto do Ollama — sem isso, um cliente podia
    injetar uma entrada `role: "system"`/`"tool"` fingindo ser uma instrução
    nossa (prompt injection via histórico). Descarta silenciosamente (com um
    aviso no log) qualquer entrada fora do formato esperado, corta `content`
    grande demais em `MAX_CARACTERES_CONTEUDO` e mantém só as últimas
    `MAX_HISTORICO_ENTRADAS` entradas válidas — nunca levanta erro, o pior
    caso é um histórico mais curto (ou vazio), nunca uma request quebrada."""
    if not isinstance(historico_bruto, list):
        return []

    validas: list[dict[str, str]] = []
    for entrada in historico_bruto:
        if (
            not isinstance(entrada, dict)
            or entrada.get("role") not in PAPEIS_HISTORICO_PERMITIDOS
            or not isinstance(entrada.get("content"), str)
        ):
            _logger.warning("Entrada de histórico do chat descartada (formato inválido): %r", entrada)
            continue
        validas.append({"role": entrada["role"], "content": entrada["content"][:MAX_CARACTERES_CONTEUDO]})

    return validas[-MAX_HISTORICO_ENTRADAS:]
