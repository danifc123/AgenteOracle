"""Rota HTTP de busca de candidatos por IA (RAG) — lógica de retrieval +
generation mora em `agent/rh/busca_candidatos.py`, este módulo só cuida do
HTTP."""

from ollama import AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.rh.busca_candidatos import ResultadoBusca, buscar_candidatos
from agente_oracle.agent.rh.embeddings import AnaliseIndisponivel
from agente_oracle.config import settings
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_rh
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.rh import candidatos as candidatos_tools


# _resultado_para_json só é usada dentro de buscar_candidatos_route, logo
# depois dela (via registrar).
def _resultado_para_json(resultado: ResultadoBusca) -> dict:
    return {
        "candidato_id": resultado.candidato_id,
        "nome": resultado.nome,
        "resumo_perfil": resultado.resumo_perfil,
        "nivel_senioridade": resultado.nivel_senioridade,
        "area_atuacao_principal": resultado.area_atuacao_principal,
        "posicao": resultado.posicao,
        "justificativa": resultado.justificativa,
        "similaridade": resultado.similaridade,
    }


def registrar(mcp) -> None:
    @mcp.custom_route("/api/rh/candidatos/buscar", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=exigir_modulo_rh)
    async def buscar_candidatos_route(request: Request, usuario: dict) -> Response:
        """Recebe a descrição de uma necessidade de vaga e devolve os
        candidatos mais adequados do pool, rankeados e justificados pela IA."""
        corpo = await request.json()
        descricao = str(corpo.get("descricao") or "").strip()
        if not descricao:
            return JSONResponse(
                {"erro": "Descreva a necessidade da vaga."}, status_code=400, headers=CORS_HEADERS
            )

        candidatos = candidatos_tools.listar_para_busca()
        ollama_client = AsyncClient(host=settings.ollama_host)

        try:
            resultados = await buscar_candidatos(
                ollama_client,
                settings.ollama_model,
                settings.ollama_embedding_model,
                descricao,
                candidatos,
            )
        except AnaliseIndisponivel as erro:
            return JSONResponse({"erro": str(erro)}, status_code=503, headers=CORS_HEADERS)

        return JSONResponse(
            [_resultado_para_json(resultado) for resultado in resultados], headers=CORS_HEADERS
        )
