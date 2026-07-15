import json
import re
from typing import Any

from mcp import ClientSession
from mcp.types import CallToolResult, Tool
from ollama import AsyncClient
from ollama import Message as OllamaMessage

from agente_oracle.config import settings

_TOOL_CALL_TAG_REGEX = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)

NOME_BANCO = "Oracle" if settings.db_backend == "oracle" else "PostgreSQL"

ESQUEMA_FINANCEIRO = """
O schema real do banco (tabelas e colunas do TOTVS) ainda não foi importado —
nenhuma tabela está liberada para consulta pelo agente neste momento.
""".strip()

SYSTEM_PROMPT = f"""Você é o Agente Oracle, um assistente do departamento financeiro. \
Use as ferramentas disponíveis para consultar dados e testar a conexão com o \
banco {NOME_BANCO} quando o usuário pedir.

{ESQUEMA_FINANCEIRO}

Enquanto isso, se o usuário pedir um relatório ou dado que dependa de consulta ao \
banco, explique de forma direta e honesta que o acesso aos dados financeiros ainda \
está sendo configurado e não está disponível no momento — NÃO tente gerar SQL, \
NÃO invente nomes de tabela/coluna e NÃO invente valores ou linhas de resultado.

Responda sempre em português."""


def mcp_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/mcp"


def tools_para_ollama(mcp_tools: list[Tool]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        }
        for tool in mcp_tools
    ]


def _conteudo_do_resultado(resultado: CallToolResult) -> str:
    partes = [bloco.text for bloco in resultado.content if getattr(bloco, "text", None)]
    return "\n".join(partes) if partes else str(resultado)


def _chamadas_normalizadas(mensagem: OllamaMessage) -> list[dict[str, Any]]:
    """Extrai as chamadas de ferramenta pedidas pelo modelo, cobrindo dois formatos:
    o mecanismo estruturado do Ollama (`mensagem.tool_calls`) e, como reforço, o
    formato em texto que o Qwen às vezes usa (`<tool_call>{"name":..,"arguments":..}</tool_call>`)
    quando não aciona o mecanismo estruturado — sem esse reforço, essas chamadas
    apareceriam como texto solto na resposta em vez de serem executadas."""
    if mensagem.tool_calls:
        return [
            {"nome": chamada.function.name, "argumentos": dict(chamada.function.arguments or {})}
            for chamada in mensagem.tool_calls
        ]

    chamadas = []
    for bloco in _TOOL_CALL_TAG_REGEX.findall(mensagem.content or ""):
        try:
            dados = json.loads(bloco)
        except json.JSONDecodeError:
            continue
        nome = dados.get("name")
        if nome:
            chamadas.append({"nome": nome, "argumentos": dados.get("arguments") or {}})
    return chamadas


async def _executar_chamadas_de_ferramenta(
    session: ClientSession, chamadas: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], str | None]:
    mensagens_resultado = []
    erro_tratado: str | None = None
    for chamada in chamadas:
        resultado = await session.call_tool(chamada["nome"], chamada["argumentos"])
        conteudo = _conteudo_do_resultado(resultado)
        mensagens_resultado.append({"role": "tool", "content": conteudo})
        if resultado.isError and erro_tratado is None:
            erro_tratado = conteudo
    return mensagens_resultado, erro_tratado


def _mensagem_para_historico(mensagem: OllamaMessage) -> dict[str, Any]:
    dados = mensagem.model_dump(exclude_none=True)
    if dados.get("content"):
        dados["content"] = _TOOL_CALL_TAG_REGEX.sub("", dados["content"]).strip()
    return dados


async def responder(
    ollama_client: AsyncClient,
    modelo: str,
    session: ClientSession,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Roda um turno completo de chat (incluindo chamadas de ferramenta em loop,
    se o modelo pedir) e devolve o histórico de mensagens atualizado, terminando
    com a resposta final do assistente, junto com a lista de ferramentas chamadas
    nesse turno (nome + argumentos, ex: o SQL usado em executar_consulta_financeira)."""
    eventos: list[dict[str, Any]] = []

    resposta = await ollama_client.chat(model=modelo, messages=messages, tools=tools)
    mensagem = resposta.message
    messages.append(_mensagem_para_historico(mensagem))

    chamadas = _chamadas_normalizadas(mensagem)
    while chamadas:
        for chamada in chamadas:
            eventos.append({"ferramenta": chamada["nome"], "argumentos": chamada["argumentos"]})

        resultados, erro_tratado = await _executar_chamadas_de_ferramenta(session, chamadas)
        messages.extend(resultados)

        if erro_tratado:
            # Devolve a mensagem de erro já tratada pela ferramenta direto pro usuário,
            # em vez de deixar o modelo reformular (e às vezes inventar) por cima dela.
            messages.append({"role": "assistant", "content": erro_tratado})
            return messages, eventos

        resposta = await ollama_client.chat(model=modelo, messages=messages, tools=tools)
        mensagem = resposta.message
        messages.append(_mensagem_para_historico(mensagem))
        chamadas = _chamadas_normalizadas(mensagem)

    return messages, eventos
