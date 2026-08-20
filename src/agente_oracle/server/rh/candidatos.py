"""Rotas HTTP do pool de candidatos do RH — lógica de dado mora em
`tools/rh/candidatos.py`, este módulo só cuida do HTTP.

`analisar_curriculo_route` chama a IA de verdade (Ollama, ver
`agent/rh/perfil_candidato.py`/`agent/rh/embeddings.py`) e só responde
quando ela termina — pode levar alguns segundos (inferência + embedding),
mas como o Angular não aguarda essa chamada antes de fechar o dialog de
upload (ver `servicos/analise-curriculo.ts` no frontend), o usuário não
fica travado — mesmo espírito da chamada síncrona e longa que
`Auditoria.buscar()` já faz contra o Ollama.
"""

from ollama import AsyncClient
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.rh.embeddings import AnaliseIndisponivel
from agente_oracle.config import settings
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_rh
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.rh import candidatos as candidatos_tools
from agente_oracle.tools.rh.extracao_curriculo import ArquivoCurriculoInvalido
from agente_oracle.tools.ti import acessos_dados

_TAMANHO_MAXIMO_ARQUIVO = 15_000_000

_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_STATUS_VALIDOS = {"ativo", "contratado", "descartado"}


def _candidato_para_json(candidato: dict) -> dict:
    resultado = dict(candidato)
    resultado["criado_em"] = candidato["criado_em"].isoformat()
    return resultado


def registrar(mcp) -> None:
    @mcp.custom_route("/api/rh/candidatos/analisar", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=exigir_modulo_rh)
    async def analisar_curriculo_route(request: Request, usuario: dict) -> Response:
        """Recebe um currículo (multipart), manda pra IA gerar o resumo de
        perfil do candidato + o embedding desse resumo, e cadastra no pool."""
        formulario = await request.form()
        arquivo = formulario.get("arquivo")
        if not isinstance(arquivo, UploadFile):
            return JSONResponse({"erro": "Envie o currículo."}, status_code=400, headers=CORS_HEADERS)

        conteudo = await arquivo.read()
        if len(conteudo) > _TAMANHO_MAXIMO_ARQUIVO:
            return JSONResponse(
                {"erro": "Arquivo muito grande (máx. 15MB)."}, status_code=400, headers=CORS_HEADERS
            )

        ollama_client = AsyncClient(host=settings.ollama_host)

        try:
            candidato = await candidatos_tools.criar_candidato(
                ollama_client,
                settings.ollama_model,
                settings.ollama_embedding_model,
                arquivo.filename or "curriculo",
                conteudo,
            )
        except ArquivoCurriculoInvalido as erro:
            return JSONResponse({"erro": str(erro)}, status_code=400, headers=CORS_HEADERS)
        except AnaliseIndisponivel as erro:
            return JSONResponse({"erro": str(erro)}, status_code=503, headers=CORS_HEADERS)

        return JSONResponse(_candidato_para_json(candidato), status_code=201, headers=CORS_HEADERS)

    @mcp.custom_route("/api/rh/candidatos/{id}/curriculo", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_rh)
    async def candidato_curriculo_route(request: Request, usuario: dict) -> Response:
        """Baixa o currículo original (PDF/DOCX) de um candidato já cadastrado."""
        try:
            id_candidato = int(request.path_params["id"])
        except ValueError:
            return JSONResponse({"erro": "Candidato não encontrado."}, status_code=404, headers=CORS_HEADERS)

        arquivo = candidatos_tools.buscar_arquivo(id_candidato)
        if arquivo is None:
            return JSONResponse({"erro": "Candidato não encontrado."}, status_code=404, headers=CORS_HEADERS)

        acessos_dados.registrar(usuario["sub"], "rh", "candidatos:curriculo", 1)
        media_type = _MEDIA_TYPES.get(arquivo["tipo_arquivo"], "application/octet-stream")
        return Response(
            content=arquivo["arquivo"],
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{arquivo["nome_arquivo"]}"',
                **CORS_HEADERS,
            },
        )

    @mcp.custom_route("/api/rh/candidatos/{id}", methods=["PATCH", "OPTIONS"])
    @rota_protegida("PATCH, OPTIONS", exigir=exigir_modulo_rh)
    async def candidato_detalhe_route(request: Request, usuario: dict) -> Response:
        """Atualiza o status (ativo/contratado/descartado) de um candidato."""
        try:
            id_candidato = int(request.path_params["id"])
        except ValueError:
            return JSONResponse({"erro": "Candidato não encontrado."}, status_code=404, headers=CORS_HEADERS)

        corpo = await request.json()
        status = str(corpo.get("status") or "").strip()
        if status not in _STATUS_VALIDOS:
            return JSONResponse({"erro": "Status inválido."}, status_code=400, headers=CORS_HEADERS)

        atualizado = candidatos_tools.atualizar_status(id_candidato, status)
        if atualizado is None:
            return JSONResponse({"erro": "Candidato não encontrado."}, status_code=404, headers=CORS_HEADERS)
        return JSONResponse(_candidato_para_json(atualizado), headers=CORS_HEADERS)

    @mcp.custom_route("/api/rh/candidatos", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_rh)
    async def candidatos_route(request: Request, usuario: dict) -> Response:
        """Lista os candidatos do pool, opcionalmente filtrados por status."""
        status = request.query_params.get("status", "").strip() or None
        candidatos = candidatos_tools.listar(status=status)
        acessos_dados.registrar(usuario["sub"], "rh", "candidatos:listar", len(candidatos))
        return JSONResponse(
            [_candidato_para_json(candidato) for candidato in candidatos], headers=CORS_HEADERS
        )
