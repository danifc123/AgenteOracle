from anyio import to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_financeiro
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.financeiro import layouts as layouts_tools


def _layout_para_json(layout: dict) -> dict:
    resultado = {chave: valor for chave, valor in layout.items() if chave != "usuario_id"}
    resultado["criado_em"] = layout["criado_em"].isoformat()
    resultado["atualizado_em"] = layout["atualizado_em"].isoformat()
    return resultado


def _layout_detalhe(metodo: str, usuario_id: int, id_layout: str, corpo: dict | None) -> Response:
    if metodo == "PATCH":
        corpo = corpo or {}
        nome = corpo.get("nome")
        if nome is not None:
            nome = str(nome).strip()
            if not nome:
                return JSONResponse(
                    {"erro": "Nome não pode ficar em branco."}, status_code=400, headers=CORS_HEADERS
                )

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


def _layouts(metodo: str, usuario_id: int, corpo: dict | None) -> Response:
    if metodo == "GET":
        layouts = layouts_tools.listar(usuario_id)
        return JSONResponse([_layout_para_json(layout) for layout in layouts], headers=CORS_HEADERS)

    corpo = corpo or {}
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
        layout = layouts_tools.criar(
            usuario_id, nome, colunas_selecionadas, valores_filtros, filiais_selecionadas
        )
    except layouts_tools.LayoutJaExiste as erro:
        return JSONResponse({"erro": str(erro)}, status_code=409, headers=CORS_HEADERS)

    return JSONResponse(_layout_para_json(layout), status_code=201, headers=CORS_HEADERS)


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/relatorio/layouts/{id}", methods=["PATCH", "DELETE", "OPTIONS"])
    @rota_protegida("PATCH, DELETE, OPTIONS", exigir=exigir_modulo_financeiro)
    async def layout_detalhe_route(request: Request, usuario: dict) -> Response:
        """Endpoint HTTP usado pra renomear/atualizar (PATCH) ou apagar
        (DELETE) um layout salvo — só o dono (usuário logado) pode mexer.
        Só o parsing do corpo (PATCH) é assíncrono de verdade; o resto
        roda em thread separada, mesmo padrão de `login_route`."""
        corpo = await request.json() if request.method == "PATCH" else None
        return await to_thread.run_sync(
            _layout_detalhe, request.method, int(usuario["sub"]), request.path_params["id"], corpo
        )

    @mcp.custom_route("/api/financeiro/relatorio/layouts", methods=["GET", "POST", "OPTIONS"])
    @rota_protegida("GET, POST, OPTIONS", exigir=exigir_modulo_financeiro)
    async def layouts_route(request: Request, usuario: dict) -> Response:
        """Endpoint HTTP usado pela tela "Criar Relatório" pra listar (GET) e
        salvar (POST) layouts — presets de colunas/filtros/filiais do
        usuário logado. Só o parsing do corpo (POST) é assíncrono de
        verdade; o resto roda em thread separada, mesmo padrão de
        `login_route`."""
        corpo = await request.json() if request.method == "POST" else None
        return await to_thread.run_sync(_layouts, request.method, int(usuario["sub"]), corpo)
