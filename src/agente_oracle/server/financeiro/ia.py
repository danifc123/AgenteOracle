from datetime import datetime

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from ollama import AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.core import mcp_url
from agente_oracle.agent.financeiro.financeiro import responder
from agente_oracle.agent.financeiro.prompt import SYSTEM_PROMPT
from agente_oracle.agent.financeiro.schema import PREFIXO_TOOL
from agente_oracle.config import settings
from agente_oracle.server.cors import CORS_HEADERS, resposta_preflight
from agente_oracle.tools.connectivity import check_oracle_connection
from agente_oracle.tools.financeiro.consulta_livre import (
    ConsultaFinanceiraInvalida,
    executar_consulta_financeira,
    exportar_consulta_financeira_xlsx,
)


def registrar(mcp) -> None:
    @mcp.tool(name=f"{PREFIXO_TOOL}testar_conexao_oracle")
    def testar_conexao_oracle() -> str:
        """Testa a conexão com o banco Oracle configurado e retorna a versão do servidor."""
        return check_oracle_connection()

    mcp.tool(name=f"{PREFIXO_TOOL}executar_consulta_financeira")(executar_consulta_financeira)

    @mcp.custom_route("/api/relatorio/exportar", methods=["POST", "OPTIONS"])
    async def exportar_relatorio_route(request: Request) -> Response:
        """Endpoint HTTP usado pelo frontend para baixar em Excel um relatório
        gerado pelo Agente Oracle no chat (roda de novo a mesma consulta validada)."""
        if request.method == "OPTIONS":
            return resposta_preflight()

        corpo = await request.json()
        sql = str(corpo.get("sql", "")).strip()

        try:
            conteudo_xlsx = exportar_consulta_financeira_xlsx(sql)
        except ConsultaFinanceiraInvalida as erro:
            return JSONResponse({"erro": str(erro)}, status_code=400, headers=CORS_HEADERS)

        nome_arquivo = f"relatorio_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{nome_arquivo}"',
                **CORS_HEADERS,
            },
        )

    @mcp.custom_route("/api/chat", methods=["POST", "OPTIONS"])
    async def chat_route(request: Request) -> JSONResponse:
        """Endpoint HTTP usado pelo frontend para conversar com o Agente Oracle."""
        if request.method == "OPTIONS":
            return resposta_preflight()

        corpo = await request.json()
        mensagem_usuario = str(corpo.get("mensagem", "")).strip()
        historico = corpo.get("historico", [])

        if not mensagem_usuario:
            return JSONResponse({"erro": "Mensagem vazia."}, status_code=400, headers=CORS_HEADERS)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *historico,
            {"role": "user", "content": mensagem_usuario},
        ]

        ollama_client = AsyncClient(host=settings.ollama_host)

        async with streamablehttp_client(mcp_url(settings.mcp_host, settings.mcp_port)) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                messages, eventos = await responder(
                    ollama_client,
                    settings.ollama_model,
                    session,
                    f"{PREFIXO_TOOL}executar_consulta_financeira",
                    f"{PREFIXO_TOOL}testar_conexao_oracle",
                    messages,
                )

        return JSONResponse(
            {"resposta": messages[-1].get("content", ""), "consultas": eventos},
            headers=CORS_HEADERS,
        )
