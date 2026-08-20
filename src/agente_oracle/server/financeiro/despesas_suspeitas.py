"""Rota da Auditoria de Despesas Suspeitas — lógica de candidato e
julgamento da IA mora em `agent/financeiro/despesas_suspeitas.py`; este
módulo só cuida do HTTP, mesmo espírito de `server/ti/seguranca.py`
(roda sob demanda, nunca em background)."""

from ollama import AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.financeiro.despesas_suspeitas import (
    AchadoDespesa,
    analisar_despesas,
    buscar_titulos_pagar,
)
from agente_oracle.config import settings
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios import _comum

_DIAS_JANELA = 90


def _achado_para_json(achado: AchadoDespesa) -> dict:
    return {
        "tipo": achado.tipo,
        "fornecedor_codigo": achado.fornecedor_codigo,
        "fornecedor_nome": achado.fornecedor_nome,
        "valor": achado.valor,
        "documentos": achado.documentos,
        "descricao": achado.descricao,
        "data_emissao_min": achado.data_emissao_min.isoformat(),
        "data_emissao_max": achado.data_emissao_max.isoformat(),
        "natureza_descricao": achado.natureza_descricao,
        "media_grupo": achado.media_grupo,
    }


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/despesas-suspeitas", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def despesas_suspeitas_route(request: Request, usuario: dict) -> Response:
        """Roda a auditoria de despesas ao vivo: busca os títulos a pagar
        dos últimos 90 dias das filiais informadas, acha candidatos de
        duplicidade/anomalia de valor (determinístico) e manda pra IA
        revisar e descrever (`agent/financeiro/despesas_suspeitas.py`)."""
        filiais = _comum.filiais_da_query(request)
        if filiais is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        titulos = buscar_titulos_pagar(filiais, _DIAS_JANELA)
        ollama_client = AsyncClient(host=settings.ollama_host)
        achados = await analisar_despesas(ollama_client, settings.ollama_model, titulos)

        _comum.registrar_acesso(usuario, "despesas_suspeitas:analisar", len(achados))
        return JSONResponse([_achado_para_json(achado) for achado in achados], headers=CORS_HEADERS)
