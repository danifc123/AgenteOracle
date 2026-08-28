import re
import unicodedata
from datetime import datetime

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from ollama import AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.core import MAX_CARACTERES_CONTEUDO, mcp_url, sanitizar_historico
from agente_oracle.agent.financeiro.financeiro import responder
from agente_oracle.agent.financeiro.prompt import SYSTEM_PROMPT
from agente_oracle.agent.financeiro.schema import PREFIXO_TOOL
from agente_oracle.config import settings
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_financeiro
from agente_oracle.server.auth.rate_limit import registrar_falha, segundos_ate_liberar
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.connectivity import check_oracle_connection
from agente_oracle.tools.financeiro import conversas_ia
from agente_oracle.tools.financeiro.consulta_livre import (
    ConsultaFinanceiraInvalida,
    executar_consulta_financeira,
    exportar_consulta_financeira_xlsx,
)

# Limites mais generosos que os do login (`server/auth/rate_limit.py` usa
# 5/3min lá) — aqui é mais uma rede de segurança contra loop/abuso do que
# uma restrição de uso normal, dado que é um punhado de usuários internos do
# time financeiro. Contam toda tentativa, sucesso ou falha (mesmo padrão de
# `criar_usuario` em `server/auth/rotas.py`), pra limitar o total de chamadas
# a Ollama/Oracle, não só as que dão erro.
LIMITE_CHAT_MENSAGENS = 30
JANELA_CHAT_SEGUNDOS = 5 * 60
LIMITE_EXPORTAR = 20
JANELA_EXPORTAR_SEGUNDOS = 5 * 60


def _resposta_limite_excedido(espera: int, mensagem: str) -> JSONResponse:
    return JSONResponse(
        {"erro": mensagem, "segundos_espera": espera},
        status_code=429,
        headers={**CORS_HEADERS, "Retry-After": str(espera)},
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
        chave_rate_limit = f"exportar_relatorio_financeiro:{usuario['usuario']}"
        espera = segundos_ate_liberar(
            chave_rate_limit, limite=LIMITE_EXPORTAR, janela_segundos=JANELA_EXPORTAR_SEGUNDOS
        )
        if espera is not None:
            return _resposta_limite_excedido(
                espera, f"Muitas exportações em pouco tempo. Tente de novo em {espera} segundos."
            )
        registrar_falha(chave_rate_limit, janela_segundos=JANELA_EXPORTAR_SEGUNDOS)

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
        chave_rate_limit = f"chat_financeiro:{usuario['usuario']}"
        espera = segundos_ate_liberar(
            chave_rate_limit, limite=LIMITE_CHAT_MENSAGENS, janela_segundos=JANELA_CHAT_SEGUNDOS
        )
        if espera is not None:
            return _resposta_limite_excedido(
                espera, f"Muitas mensagens em pouco tempo. Tente de novo em {espera} segundos."
            )
        registrar_falha(chave_rate_limit, janela_segundos=JANELA_CHAT_SEGUNDOS)

        corpo = await request.json()
        mensagem_usuario = str(corpo.get("mensagem", "")).strip()
        historico = sanitizar_historico(corpo.get("historico", []))

        if not mensagem_usuario:
            return JSONResponse({"erro": "Mensagem vazia."}, status_code=400, headers=CORS_HEADERS)
        if len(mensagem_usuario) > MAX_CARACTERES_CONTEUDO:
            return JSONResponse({"erro": "Mensagem muito longa."}, status_code=400, headers=CORS_HEADERS)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *historico,
            {"role": "user", "content": mensagem_usuario},
        ]

        ollama_client = AsyncClient(host=settings.ollama_host)

        try:
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
        except ConnectionError:
            # Ollama fora do ar/inacessível — diferente de `analisar_perfis`
            # (Auditoria), aqui não tem como degradar silenciosamente pra uma
            # resposta vazia: o chat inteiro depende da IA responder algo.
            # Devolve 503 em vez de deixar a ConnectionError subir crua (vira
            # 500 sem corpo tratado).
            return JSONResponse(
                {"erro": "Assistente de IA indisponível no momento. Tente novamente em instantes."},
                status_code=503,
                headers=CORS_HEADERS,
            )

        resposta_final = messages[-1].get("content", "")
        conversas_ia.registrar(usuario["usuario"], mensagem_usuario, resposta_final, eventos)

        return JSONResponse(
            {"resposta": resposta_final, "consultas": eventos},
            headers=CORS_HEADERS,
        )
