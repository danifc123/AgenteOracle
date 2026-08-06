"""Rota de upload livre (qualquer .xlsx, sem relação com views do sistema)
que junta duas planilhas numa terceira — ver
`tools/ferramentas/juntar_excel.py` para a lógica de junção em si. Disponível
pra qualquer usuário autenticado, sem exigir módulo específico."""

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.dependencia import exigir_usuario
from agente_oracle.server.cors import CORS_HEADERS, resposta_preflight
from agente_oracle.tools.auth.papeis import sigla_usuario
from agente_oracle.tools.ferramentas.juntar_excel import ArquivoExcelInvalido, analisar_colunas, juntar_planilhas

_TAMANHO_MAXIMO_ARQUIVO = 15_000_000


async def _extrair_arquivos(request: Request) -> tuple[bytes, bytes] | JSONResponse:
    formulario = await request.form()
    arquivo1 = formulario.get("arquivo1")
    arquivo2 = formulario.get("arquivo2")
    if not isinstance(arquivo1, UploadFile) or not isinstance(arquivo2, UploadFile):
        return JSONResponse({"erro": "Envie os dois arquivos."}, status_code=400, headers=CORS_HEADERS)

    conteudo1 = await arquivo1.read()
    conteudo2 = await arquivo2.read()
    if len(conteudo1) > _TAMANHO_MAXIMO_ARQUIVO or len(conteudo2) > _TAMANHO_MAXIMO_ARQUIVO:
        return JSONResponse({"erro": "Arquivo muito grande (máx. 15MB)."}, status_code=400, headers=CORS_HEADERS)

    return conteudo1, conteudo2


def registrar(mcp) -> None:
    @mcp.custom_route("/api/ferramentas/juntar-excel", methods=["POST", "OPTIONS"])
    async def juntar_excel_route(request: Request) -> Response:
        if request.method == "OPTIONS":
            return resposta_preflight()

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        arquivos_ou_erro = await _extrair_arquivos(request)
        if isinstance(arquivos_ou_erro, JSONResponse):
            return arquivos_ou_erro
        conteudo1, conteudo2 = arquivos_ou_erro

        try:
            resultado = juntar_planilhas(conteudo1, conteudo2)
        except ArquivoExcelInvalido as erro:
            return JSONResponse({"erro": str(erro)}, status_code=400, headers=CORS_HEADERS)

        sigla = sigla_usuario(usuario_ou_erro.get("papeis", []))
        nome_arquivo = f"planilhas_combinadas_{sigla}.xlsx" if sigla else "planilhas_combinadas.xlsx"

        return Response(
            content=resultado,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"', **CORS_HEADERS},
        )

    @mcp.custom_route("/api/ferramentas/juntar-excel/analisar", methods=["POST", "OPTIONS"])
    async def analisar_juntar_excel_route(request: Request) -> Response:
        if request.method == "OPTIONS":
            return resposta_preflight()

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        arquivos_ou_erro = await _extrair_arquivos(request)
        if isinstance(arquivos_ou_erro, JSONResponse):
            return arquivos_ou_erro
        conteudo1, conteudo2 = arquivos_ou_erro

        try:
            analise = analisar_colunas(conteudo1, conteudo2)
        except ArquivoExcelInvalido as erro:
            return JSONResponse({"erro": str(erro)}, status_code=400, headers=CORS_HEADERS)

        return JSONResponse(analise, headers=CORS_HEADERS)
