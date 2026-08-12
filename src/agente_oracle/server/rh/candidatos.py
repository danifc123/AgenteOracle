"""Rotas HTTP de análise/listagem de candidatos do RH — lógica de dado mora
em `tools/rh/candidatos.py`, este módulo só cuida do HTTP.

O `asyncio.sleep` em `analisar_curriculo_route` simula o tempo de
processamento de uma IA de verdade (ainda não existe — ver docstring de
`tools/rh/candidatos.py`) sem precisar de fila/job assíncrono: a resposta
HTTP só chega quando "termina", mas como o Angular não aguarda essa
chamada antes de fechar o dialog de upload (ver `servicos/analise-curriculo.ts`
no frontend), o usuário não fica travado — mesmo espírito da chamada
síncrona e longa que `Auditoria.buscar()` já faz contra o Ollama.
"""

import asyncio
import random

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_rh
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.rh import candidatos as candidatos_tools

_TAMANHO_MAXIMO_ARQUIVO = 15_000_000
_DURACAO_MOCK_SEGUNDOS = (4, 8)


def _candidato_para_json(candidato: dict) -> dict:
    resultado = dict(candidato)
    resultado["criado_em"] = candidato["criado_em"].isoformat()
    return resultado


def registrar(mcp) -> None:
    @mcp.custom_route("/api/rh/candidatos/analisar", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=exigir_modulo_rh)
    async def analisar_curriculo_route(request: Request, usuario: dict) -> Response:
        """Recebe o currículo (multipart) + a vaga escolhida, "analisa" (mock)
        contra todas as vagas ativas e cadastra o candidato se a melhor
        compatibilidade encontrada bater o limite mínimo."""
        formulario = await request.form()
        arquivo = formulario.get("arquivo")
        if not isinstance(arquivo, UploadFile):
            return JSONResponse({"erro": "Envie o currículo."}, status_code=400, headers=CORS_HEADERS)

        try:
            vaga_id = int(formulario.get("vaga_id", ""))
        except (TypeError, ValueError):
            return JSONResponse({"erro": "Informe a vaga."}, status_code=400, headers=CORS_HEADERS)

        conteudo = await arquivo.read()
        if len(conteudo) > _TAMANHO_MAXIMO_ARQUIVO:
            return JSONResponse(
                {"erro": "Arquivo muito grande (máx. 15MB)."}, status_code=400, headers=CORS_HEADERS
            )

        await asyncio.sleep(random.uniform(*_DURACAO_MOCK_SEGUNDOS))

        try:
            candidato = candidatos_tools.criar_candidato(vaga_id, arquivo.filename or "curriculo")
        except candidatos_tools.SemVagaAtiva as erro:
            return JSONResponse({"erro": str(erro)}, status_code=400, headers=CORS_HEADERS)

        return JSONResponse(_candidato_para_json(candidato), status_code=201, headers=CORS_HEADERS)

    @mcp.custom_route("/api/rh/candidatos/{id}", methods=["PATCH", "OPTIONS"])
    @rota_protegida("PATCH, OPTIONS", exigir=exigir_modulo_rh)
    async def candidato_detalhe_route(request: Request, usuario: dict) -> Response:
        """Atualiza o status (pendente/avancado/descartado) de um candidato."""
        try:
            id_candidato = int(request.path_params["id"])
        except ValueError:
            return JSONResponse({"erro": "Candidato não encontrado."}, status_code=404, headers=CORS_HEADERS)

        corpo = await request.json()
        status = str(corpo.get("status") or "").strip()
        if status not in {"pendente", "avancado", "descartado"}:
            return JSONResponse({"erro": "Status inválido."}, status_code=400, headers=CORS_HEADERS)

        atualizado = candidatos_tools.atualizar_status(id_candidato, status)
        if atualizado is None:
            return JSONResponse({"erro": "Candidato não encontrado."}, status_code=404, headers=CORS_HEADERS)
        return JSONResponse(_candidato_para_json(atualizado), headers=CORS_HEADERS)

    @mcp.custom_route("/api/rh/candidatos", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_rh)
    async def candidatos_route(request: Request, usuario: dict) -> Response:
        """Lista os candidatos já cadastrados (salvos) pra uma vaga."""
        try:
            vaga_id = int(request.query_params.get("vaga_id", ""))
        except ValueError:
            return JSONResponse({"erro": "Informe vaga_id."}, status_code=400, headers=CORS_HEADERS)

        candidatos = candidatos_tools.listar(vaga_id)
        return JSONResponse(
            [_candidato_para_json(candidato) for candidato in candidatos], headers=CORS_HEADERS
        )
