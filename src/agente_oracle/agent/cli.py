import asyncio
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult, Tool
from ollama import AsyncClient
from ollama import Message as OllamaMessage

from agente_oracle.config import settings

SYSTEM_PROMPT = (
    "Você é o Agente Oracle, um assistente do departamento financeiro. "
    "Use as ferramentas disponíveis para consultar transações e testar a conexão "
    "com o banco Oracle quando o usuário pedir. Responda sempre em português, "
    "de forma direta e objetiva."
)


def _mcp_url() -> str:
    return f"http://{settings.mcp_host}:{settings.mcp_port}/mcp"


def _tools_para_ollama(mcp_tools: list[Tool]) -> list[dict[str, Any]]:
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


async def _executar_chamadas_de_ferramenta(session: ClientSession, tool_calls: list) -> list[dict[str, Any]]:
    mensagens_resultado = []
    for chamada in tool_calls:
        nome = chamada.function.name
        argumentos = chamada.function.arguments or {}
        print(f"  [ferramenta] chamando {nome}({argumentos})")
        resultado = await session.call_tool(nome, argumentos)
        mensagens_resultado.append({"role": "tool", "content": _conteudo_do_resultado(resultado)})
    return mensagens_resultado


def _mensagem_para_historico(mensagem: OllamaMessage) -> dict[str, Any]:
    return mensagem.model_dump(exclude_none=True)


async def executar_chat() -> None:
    ollama_client = AsyncClient(host=settings.ollama_host)

    async with streamablehttp_client(_mcp_url()) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            tools = _tools_para_ollama(tools_result.tools)

            print(f"Agente Oracle pronto (modelo: {settings.ollama_model}). Digite 'sair' para encerrar.\n")

            messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

            while True:
                entrada = input("Você: ").strip()
                if entrada.lower() in {"sair", "exit", "quit"}:
                    break
                if not entrada:
                    continue

                messages.append({"role": "user", "content": entrada})

                resposta = await ollama_client.chat(model=settings.ollama_model, messages=messages, tools=tools)
                mensagem = resposta.message
                messages.append(_mensagem_para_historico(mensagem))

                while mensagem.tool_calls:
                    resultados = await _executar_chamadas_de_ferramenta(session, mensagem.tool_calls)
                    messages.extend(resultados)
                    resposta = await ollama_client.chat(model=settings.ollama_model, messages=messages, tools=tools)
                    mensagem = resposta.message
                    messages.append(_mensagem_para_historico(mensagem))

                print(f"Agente: {mensagem.content}\n")


def main() -> None:
    asyncio.run(executar_chat())


if __name__ == "__main__":
    main()
