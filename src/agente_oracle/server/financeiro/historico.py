from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.auth.dependencia import exigir_usuario
from agente_oracle.server.cors import CORS_HEADERS, resposta_preflight
from agente_oracle.tools.financeiro import historico as historico_tools


def _historico_para_json(documento: dict) -> dict:
    resultado = {chave: valor for chave, valor in documento.items() if chave not in {"_id", "hash_sql"}}
    resultado["id"] = str(documento["_id"])
    resultado["criado_em"] = documento["criado_em"].isoformat()
    expira_em = documento.get("expira_em")
    resultado["expira_em"] = expira_em.isoformat() if expira_em else None
    return resultado


def registrar(mcp) -> None:
    @mcp.custom_route("/api/relatorios/historico", methods=["GET", "OPTIONS"])
    async def listar_historico_route(request: Request) -> Response:
        """Endpoint HTTP usado pela tela de histórico para listar os relatórios já gerados pela IA."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        documentos = historico_tools.listar()
        return JSONResponse([_historico_para_json(doc) for doc in documentos], headers=CORS_HEADERS)

    @mcp.custom_route("/api/relatorios/historico/{id}/exportar", methods=["GET", "OPTIONS"])
    async def exportar_historico_route(request: Request) -> Response:
        """Endpoint HTTP usado pela tela de histórico para baixar em Excel um
        relatório já salvo, sem rodar a consulta de novo no Oracle."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        documento = historico_tools.obter(request.path_params["id"])
        if documento is None:
            return JSONResponse({"erro": "Relatório não encontrado no histórico."}, status_code=404, headers=CORS_HEADERS)

        conteudo_xlsx = gerar_xlsx(documento["colunas"], documento["linhas"], titulo="Relatório")
        nome_arquivo = f"relatorio_{documento['_id']}.xlsx"
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{nome_arquivo}"',
                **CORS_HEADERS,
            },
        )

    @mcp.custom_route("/api/relatorios/historico/{id}", methods=["PATCH", "DELETE", "OPTIONS"])
    async def atualizar_ou_deletar_historico_route(request: Request) -> Response:
        """Endpoint HTTP usado pela tela de histórico para apagar (DELETE) um
        relatório salvo, ou fixar/desfixar (PATCH `{"fixado": bool}`) — um
        relatório fixado não expira pelo TTL de 15h."""
        if request.method == "OPTIONS":
            return resposta_preflight("PATCH, DELETE, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        id_relatorio = request.path_params["id"]

        if request.method == "PATCH":
            corpo = await request.json()
            fixado = bool(corpo.get("fixado"))
            atualizado = historico_tools.fixar(id_relatorio) if fixado else historico_tools.desfixar(id_relatorio)
            if not atualizado:
                return JSONResponse({"erro": "Relatório não encontrado no histórico."}, status_code=404, headers=CORS_HEADERS)
            return JSONResponse({"ok": True}, headers=CORS_HEADERS)

        apagado = historico_tools.deletar(id_relatorio)
        if not apagado:
            return JSONResponse({"erro": "Relatório não encontrado no histórico."}, status_code=404, headers=CORS_HEADERS)
        return JSONResponse({"ok": True}, headers=CORS_HEADERS)
