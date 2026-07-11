from datetime import datetime

from mcp.server.fastmcp import FastMCP
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from ollama import AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.core import SYSTEM_PROMPT, mcp_url, responder, tools_para_ollama
from agente_oracle.config import settings
from agente_oracle.tools.connectivity import check_oracle_connection
from agente_oracle.tools.consulta_livre import (
    ConsultaFinanceiraInvalida,
    executar_consulta_financeira,
    exportar_consulta_financeira_xlsx,
)
from agente_oracle.tools.financeiro import exportar_transacoes_xlsx, listar_transacoes_json

mcp = FastMCP("agente-oracle", host=settings.mcp_host, port=settings.mcp_port)

_CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}


def _resposta_preflight() -> JSONResponse:
    return JSONResponse(
        {},
        headers={
            **_CORS_HEADERS,
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
    )


@mcp.tool()
def testar_conexao_oracle() -> str:
    """Testa a conexão com o banco Oracle configurado e retorna a versão do servidor."""
    return check_oracle_connection()


mcp.tool()(executar_consulta_financeira)


@mcp.custom_route("/api/transacoes", methods=["GET"])
async def listar_transacoes_route(request: Request) -> JSONResponse:
    """Endpoint HTTP usado pelo frontend para preencher a tabela de transações."""
    limite = int(request.query_params.get("limite", 20))
    transacoes = listar_transacoes_json(limite)
    return JSONResponse(transacoes, headers=_CORS_HEADERS)


@mcp.custom_route("/api/transacoes/exportar", methods=["GET"])
async def exportar_transacoes_route(request: Request) -> Response:
    """Endpoint HTTP usado pelo frontend para baixar o relatório de transações em Excel."""
    limite = int(request.query_params.get("limite", 20))
    conteudo_xlsx, nome_arquivo = exportar_transacoes_xlsx(limite)
    return Response(
        content=conteudo_xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{nome_arquivo}"',
            **_CORS_HEADERS,
        },
    )


@mcp.custom_route("/api/relatorio/exportar", methods=["POST", "OPTIONS"])
async def exportar_relatorio_route(request: Request) -> Response:
    """Endpoint HTTP usado pelo frontend para baixar em Excel um relatório
    gerado pelo Agente Oracle no chat (roda de novo a mesma consulta validada)."""
    if request.method == "OPTIONS":
        return _resposta_preflight()

    corpo = await request.json()
    sql = str(corpo.get("sql", "")).strip()

    try:
        conteudo_xlsx = exportar_consulta_financeira_xlsx(sql)
    except ConsultaFinanceiraInvalida as erro:
        return JSONResponse({"erro": str(erro)}, status_code=400, headers=_CORS_HEADERS)

    nome_arquivo = f"relatorio_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    return Response(
        content=conteudo_xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{nome_arquivo}"',
            **_CORS_HEADERS,
        },
    )


@mcp.custom_route("/api/chat", methods=["POST", "OPTIONS"])
async def chat_route(request: Request) -> JSONResponse:
    """Endpoint HTTP usado pelo frontend para conversar com o Agente Oracle."""
    if request.method == "OPTIONS":
        return _resposta_preflight()

    corpo = await request.json()
    mensagem_usuario = str(corpo.get("mensagem", "")).strip()
    historico = corpo.get("historico", [])

    if not mensagem_usuario:
        return JSONResponse({"erro": "Mensagem vazia."}, status_code=400, headers=_CORS_HEADERS)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *historico, {"role": "user", "content": mensagem_usuario}]

    ollama_client = AsyncClient(host=settings.ollama_host)

    async with streamablehttp_client(mcp_url(settings.mcp_host, settings.mcp_port)) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            tools = tools_para_ollama(tools_result.tools)
            messages, eventos = await responder(ollama_client, settings.ollama_model, session, tools, messages)

    return JSONResponse(
        {"resposta": messages[-1].get("content", ""), "consultas": eventos},
        headers=_CORS_HEADERS,
    )


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
