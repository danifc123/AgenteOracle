"""Rotas HTTP do cadastro de vagas críticas do RH — lógica de acesso a dado
mora em `tools/rh/vagas.py`, este módulo só cuida do HTTP."""

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_rh
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.rh import vagas as vagas_tools


def _vaga_para_json(vaga: dict) -> dict:
    resultado = dict(vaga)
    resultado["criado_em"] = vaga["criado_em"].isoformat()
    return resultado


def registrar(mcp) -> None:
    @mcp.custom_route("/api/rh/vagas/{id}", methods=["PATCH", "DELETE", "OPTIONS"])
    @rota_protegida("PATCH, DELETE, OPTIONS", exigir=exigir_modulo_rh)
    async def vaga_detalhe_route(request: Request, usuario: dict) -> Response:
        """Atualiza (PATCH) ou apaga (DELETE) uma vaga cadastrada."""
        try:
            id_vaga = int(request.path_params["id"])
        except ValueError:
            return JSONResponse({"erro": "Vaga não encontrada."}, status_code=404, headers=CORS_HEADERS)

        if request.method == "PATCH":
            corpo = await request.json()
            atualizada = vagas_tools.atualizar(
                id_vaga,
                titulo=corpo.get("titulo"),
                localizacao=corpo.get("localizacao"),
                ativa=corpo.get("ativa"),
            )
            if atualizada is None:
                return JSONResponse({"erro": "Vaga não encontrada."}, status_code=404, headers=CORS_HEADERS)
            return JSONResponse(_vaga_para_json(atualizada), headers=CORS_HEADERS)

        try:
            apagada = vagas_tools.deletar(id_vaga)
        except vagas_tools.VagaComCandidatosVinculados as erro:
            return JSONResponse({"erro": str(erro)}, status_code=409, headers=CORS_HEADERS)

        if not apagada:
            return JSONResponse({"erro": "Vaga não encontrada."}, status_code=404, headers=CORS_HEADERS)
        return JSONResponse({"ok": True}, headers=CORS_HEADERS)

    @mcp.custom_route("/api/rh/vagas", methods=["GET", "POST", "OPTIONS"])
    @rota_protegida("GET, POST, OPTIONS", exigir=exigir_modulo_rh)
    async def vagas_route(request: Request, usuario: dict) -> Response:
        """Lista (GET) e cadastra (POST) vagas críticas."""
        if request.method == "GET":
            vagas = vagas_tools.listar()
            return JSONResponse([_vaga_para_json(vaga) for vaga in vagas], headers=CORS_HEADERS)

        corpo = await request.json()
        titulo = str(corpo.get("titulo") or "").strip()
        localizacao = str(corpo.get("localizacao") or "").strip()

        if not titulo or not localizacao:
            return JSONResponse(
                {"erro": "Informe título e localização da vaga."}, status_code=400, headers=CORS_HEADERS
            )

        vaga = vagas_tools.criar(titulo, localizacao)
        return JSONResponse(_vaga_para_json(vaga), status_code=201, headers=CORS_HEADERS)
