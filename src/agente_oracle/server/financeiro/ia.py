import re
import unicodedata
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
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_financeiro
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.connectivity import check_oracle_connection
from agente_oracle.tools.financeiro.consulta_livre import (
    ConsultaFinanceiraInvalida,
    executar_consulta_financeira,
    exportar_consulta_financeira_xlsx,
)


def _nome_arquivo_a_partir_do_titulo(titulo: str) -> str:
    """Deriva o nome do arquivo baixado a partir do título que a IA deu ao
    relatório no chat (ex: "Últimas Transações Pagas" -> "Ultimas Transacoes
    Pagas.xlsx") — sem acentos nem caracteres inválidos em nome de arquivo.
    Sem título, cai de volta no padrão antigo com timestamp."""
    sem_acento = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode("ascii")
    limpo = re.sub(r'[\\/:*?"<>|]', "", sem_acento).strip()
    limpo = re.sub(r"\s+", " ", limpo)
    if not limpo:
        return f"relatorio_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    return f"{limpo}.xlsx"


def registrar(mcp) -> None:
    @mcp.tool(name=f"{PREFIXO_TOOL}testar_conexao_oracle")
    def testar_conexao_oracle() -> str:
        """Testa a conexão com o banco Oracle configurado e retorna a versão do servidor."""
        return check_oracle_connection()

    mcp.tool(name=f"{PREFIXO_TOOL}executar_consulta_financeira")(executar_consulta_financeira)

    @mcp.custom_route("/api/financeiro/relatorio/exportar", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=exigir_modulo_financeiro)
    async def exportar_relatorio_route(request: Request, usuario: dict) -> Response:
        """Endpoint HTTP usado pelo frontend para baixar em Excel um relatório
        gerado pelo Agente Oracle no chat (roda de novo a mesma consulta validada)."""
        corpo = await request.json()
        sql = str(corpo.get("sql", "")).strip()
        titulo = str(corpo.get("titulo", "")).strip()

        try:
            conteudo_xlsx = exportar_consulta_financeira_xlsx(sql)
        except ConsultaFinanceiraInvalida as erro:
            return JSONResponse({"erro": str(erro)}, status_code=400, headers=CORS_HEADERS)

        nome_arquivo = _nome_arquivo_a_partir_do_titulo(titulo)
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{nome_arquivo}"',
                **CORS_HEADERS,
            },
        )

    @mcp.custom_route("/api/financeiro/chat", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=exigir_modulo_financeiro)
    async def chat_route(request: Request, usuario: dict) -> JSONResponse:
        """Endpoint HTTP usado pelo frontend para conversar com o Agente Oracle."""
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

        async with (
            streamablehttp_client(mcp_url(settings.mcp_host, settings.mcp_port)) as (
                read_stream,
                write_stream,
                _,
            ),
            ClientSession(read_stream, write_stream) as session,
        ):
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
