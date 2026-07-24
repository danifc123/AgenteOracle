from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.dependencia import exigir_usuario
from agente_oracle.server.cors import CORS_HEADERS, resposta_preflight
from agente_oracle.tools.financeiro import layouts as layouts_tools


def _layout_para_json(layout: dict) -> dict:
    resultado = {chave: valor for chave, valor in layout.items() if chave != "usuario_id"}
    resultado["criado_em"] = layout["criado_em"].isoformat()
    resultado["atualizado_em"] = layout["atualizado_em"].isoformat()
    return resultado


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/relatorio/layouts", methods=["GET", "POST", "OPTIONS"])
    async def layouts_route(request: Request) -> Response:
        """Endpoint HTTP usado pela tela "Criar Relatório" pra listar (GET) e
        salvar (POST) layouts — presets de colunas/filtros/filiais do usuário logado."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, POST, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro
        usuario_id = int(usuario_ou_erro["sub"])

        if request.method == "GET":
            layouts = layouts_tools.listar(usuario_id)
            return JSONResponse([_layout_para_json(layout) for layout in layouts], headers=CORS_HEADERS)

        corpo = await request.json()
        nome = str(corpo.get("nome") or "").strip()
        colunas_selecionadas = corpo.get("colunas_selecionadas")
        valores_filtros = corpo.get("valores_filtros") or {}
        filiais_selecionadas = corpo.get("filiais_selecionadas") or []

        if not nome or not isinstance(colunas_selecionadas, dict) or not colunas_selecionadas:
            return JSONResponse(
                {"erro": "Informe um nome e ao menos uma coluna selecionada."},
                status_code=400,
                headers=CORS_HEADERS,
            )

        try:
            layout = layouts_tools.criar(usuario_id, nome, colunas_selecionadas, valores_filtros, filiais_selecionadas)
        except layouts_tools.LayoutJaExiste as erro:
            return JSONResponse({"erro": str(erro)}, status_code=409, headers=CORS_HEADERS)

        return JSONResponse(_layout_para_json(layout), status_code=201, headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/relatorio/layouts/{id}", methods=["PATCH", "DELETE", "OPTIONS"])
    async def layout_detalhe_route(request: Request) -> Response:
        """Endpoint HTTP usado pra renomear/atualizar (PATCH) ou apagar
        (DELETE) um layout salvo — só o dono (usuário logado) pode mexer."""
        if request.method == "OPTIONS":
            return resposta_preflight("PATCH, DELETE, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro
        usuario_id = int(usuario_ou_erro["sub"])

        id_layout = request.path_params["id"]

        if request.method == "PATCH":
            corpo = await request.json()
            nome = corpo.get("nome")
            if nome is not None:
                nome = str(nome).strip()
                if not nome:
                    return JSONResponse({"erro": "Nome não pode ficar em branco."}, status_code=400, headers=CORS_HEADERS)

            try:
                atualizado = layouts_tools.atualizar(
                    usuario_id,
                    id_layout,
                    nome=nome,
                    colunas_selecionadas=corpo.get("colunas_selecionadas"),
                    valores_filtros=corpo.get("valores_filtros"),
                    filiais_selecionadas=corpo.get("filiais_selecionadas"),
                )
            except layouts_tools.LayoutJaExiste as erro:
                return JSONResponse({"erro": str(erro)}, status_code=409, headers=CORS_HEADERS)

            if atualizado is None:
                return JSONResponse({"erro": "Layout não encontrado."}, status_code=404, headers=CORS_HEADERS)
            return JSONResponse(_layout_para_json(atualizado), headers=CORS_HEADERS)

        apagado = layouts_tools.deletar(usuario_id, id_layout)
        if not apagado:
            return JSONResponse({"erro": "Layout não encontrado."}, status_code=404, headers=CORS_HEADERS)
        return JSONResponse({"ok": True}, headers=CORS_HEADERS)
