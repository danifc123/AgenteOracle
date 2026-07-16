import asyncio
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from ollama import AsyncClient

from agente_oracle.agent.core import mcp_url, responder, tools_para_ollama
from agente_oracle.agent.financeiro.prompt import SYSTEM_PROMPT
from agente_oracle.config import settings


async def executar_chat() -> None:
    ollama_client = AsyncClient(host=settings.ollama_host)

    async with streamablehttp_client(mcp_url(settings.mcp_host, settings.mcp_port)) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            tools = tools_para_ollama(tools_result.tools)

            print(f"Agente Oracle pronto (modelo: {settings.ollama_model}). Digite 'sair' para encerrar.\n")

            messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

            while True:
                entrada = input("Você: ").strip()
                if entrada.lower() in {"sair", "exit", "quit"}:
                    break
                if not entrada:
                    continue

                messages.append({"role": "user", "content": entrada})
                messages, eventos = await responder(ollama_client, settings.ollama_model, session, tools, messages)

                for evento in eventos:
                    print(f"  [ferramenta] {evento['ferramenta']}({evento['argumentos']})")

                print(f"Agente: {messages[-1].get('content', '')}\n")


def main() -> None:
    asyncio.run(executar_chat())


if __name__ == "__main__":
    main()
