import json
import re
from typing import Any

from mcp import ClientSession
from mcp.types import CallToolResult, Tool
from ollama import AsyncClient
from ollama import Message as OllamaMessage

_TOOL_CALL_TAG_REGEX = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


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
    session: ClientSession, chamadas: list[dict[str, Any]], nomes_permitidos: set[str]
) -> tuple[list[dict[str, Any]], str | None]:
    """Executa as chamadas pedidas pelo modelo — mas só as que estão em
    `nomes_permitidos` (as tools que de fato foram oferecidas a ele neste turno).
    A sessão MCP em si enxerga as tools de todos os módulos registrados no
    mesmo servidor, então essa checagem é o que garante, na prática, que o
    agente de um módulo não acabe chamando a tool de outro — filtrar só a
    lista mostrada ao modelo não seria suficiente por si só."""
    mensagens_resultado = []
    erro_tratado: str | None = None
    for chamada in chamadas:
        if chamada["nome"] not in nomes_permitidos:
            conteudo = f"Ferramenta '{chamada['nome']}' não está disponível neste contexto."
            mensagens_resultado.append({"role": "tool", "content": conteudo})
            if erro_tratado is None:
                erro_tratado = conteudo
            continue

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
    nomes_permitidos = {tool["function"]["name"] for tool in tools}

    resposta = await ollama_client.chat(model=modelo, messages=messages, tools=tools)
    mensagem = resposta.message
    messages.append(_mensagem_para_historico(mensagem))

    chamadas = _chamadas_normalizadas(mensagem)
    while chamadas:
        for chamada in chamadas:
            evento = {"ferramenta": chamada["nome"], "argumentos": chamada["argumentos"]}
            # O modelo às vezes repete a mesma chamada (mesmo nome + mesmos
            # argumentos) em mais de uma rodada antes de finalizar a resposta.
            # Sem essa checagem, o front mostraria um botão "Baixar em Excel"
            # duplicado pra cada repetição, mesmo gerando o mesmo relatório.
            if evento not in eventos:
                eventos.append(evento)

        resultados, erro_tratado = await _executar_chamadas_de_ferramenta(session, chamadas, nomes_permitidos)
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
