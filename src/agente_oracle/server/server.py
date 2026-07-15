from datetime import datetime

from mcp.server.fastmcp import FastMCP
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from ollama import AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.core import SYSTEM_PROMPT, mcp_url, responder, tools_para_ollama
from agente_oracle.config import settings
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.tools import historico as historico_tools
from agente_oracle.tools.connectivity import check_oracle_connection
from agente_oracle.tools.consulta_livre import (
    ConsultaFinanceiraInvalida,
    executar_consulta_financeira,
    exportar_consulta_financeira_xlsx,
)

mcp = FastMCP("agente-oracle", host=settings.mcp_host, port=settings.mcp_port)

_CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}


def _resposta_preflight(metodos: str = "POST, OPTIONS") -> JSONResponse:
    return JSONResponse(
        {},
        headers={
            **_CORS_HEADERS,
            "Access-Control-Allow-Methods": metodos,
            "Access-Control-Allow-Headers": "Content-Type",
        },
    )


def _historico_para_json(documento: dict) -> dict:
    resultado = {chave: valor for chave, valor in documento.items() if chave not in {"_id", "hash_sql"}}
    resultado["id"] = str(documento["_id"])
    resultado["criado_em"] = documento["criado_em"].isoformat()
    expira_em = documento.get("expira_em")
    resultado["expira_em"] = expira_em.isoformat() if expira_em else None
    return resultado


@mcp.tool()
def testar_conexao_oracle() -> str:
    """Testa a conexão com o banco Oracle configurado e retorna a versão do servidor."""
    return check_oracle_connection()


mcp.tool()(executar_consulta_financeira)


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


@mcp.custom_route("/api/relatorios/historico", methods=["GET"])
async def listar_historico_route(request: Request) -> JSONResponse:
    """Endpoint HTTP usado pela tela de histórico para listar os relatórios já gerados pela IA."""
    documentos = historico_tools.listar()
    return JSONResponse([_historico_para_json(doc) for doc in documentos], headers=_CORS_HEADERS)


@mcp.custom_route("/api/relatorios/historico/{id}/exportar", methods=["GET"])
async def exportar_historico_route(request: Request) -> Response:
    """Endpoint HTTP usado pela tela de histórico para baixar em Excel um
    relatório já salvo, sem rodar a consulta de novo no Oracle."""
    documento = historico_tools.obter(request.path_params["id"])
    if documento is None:
        return JSONResponse({"erro": "Relatório não encontrado no histórico."}, status_code=404, headers=_CORS_HEADERS)

    conteudo_xlsx = gerar_xlsx(documento["colunas"], documento["linhas"], titulo="Relatório")
    nome_arquivo = f"relatorio_{documento['_id']}.xlsx"
    return Response(
        content=conteudo_xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{nome_arquivo}"',
            **_CORS_HEADERS,
        },
    )


@mcp.custom_route("/api/relatorios/historico/{id}", methods=["PATCH", "DELETE", "OPTIONS"])
async def atualizar_ou_deletar_historico_route(request: Request) -> Response:
    """Endpoint HTTP usado pela tela de histórico para apagar (DELETE) um
    relatório salvo, ou fixar/desfixar (PATCH `{"fixado": bool}`) — um
    relatório fixado não expira pelo TTL de 15h."""
    if request.method == "OPTIONS":
        return _resposta_preflight("PATCH, DELETE, OPTIONS")

    id_relatorio = request.path_params["id"]

    if request.method == "PATCH":
        corpo = await request.json()
        fixado = bool(corpo.get("fixado"))
        atualizado = historico_tools.fixar(id_relatorio) if fixado else historico_tools.desfixar(id_relatorio)
        if not atualizado:
            return JSONResponse({"erro": "Relatório não encontrado no histórico."}, status_code=404, headers=_CORS_HEADERS)
        return JSONResponse({"ok": True}, headers=_CORS_HEADERS)

    apagado = historico_tools.deletar(id_relatorio)
    if not apagado:
        return JSONResponse({"erro": "Relatório não encontrado no histórico."}, status_code=404, headers=_CORS_HEADERS)
    return JSONResponse({"ok": True}, headers=_CORS_HEADERS)


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
