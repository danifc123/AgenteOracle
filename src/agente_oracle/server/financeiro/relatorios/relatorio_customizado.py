"""Rotas HTTP do construtor de relatório sob demanda para a tela "Criar
Relatório": o usuário escolhe colunas de uma ou mais views financeiras
liberadas (`agent/financeiro/schema.py` — o mesmo registro que a IA usa em
`consulta_livre`) e monta um relatório com os JOINs resolvidos
automaticamente pelos relacionamentos declarados entre as views. A lógica de
validação/montagem de SQL em si mora em `relatorio_customizado_sql.py` — este
módulo só cuida do HTTP (parsing de request, status code, resposta)."""

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.financeiro.schema import VIEWS_DISPONIVEIS, inferir_tipo_filtro
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.relatorio_customizado_sql import (
    RelatorioCustomizadoInvalido,
    buscar_opcoes_coluna,
    buscar_relatorio_customizado,
    parametros_da_query,
    validar_coluna,
)

_ERRO_PARAMETROS = (
    "Informe ao menos uma filial e uma coluna válida (formato view.coluna) — "
    "e, se enviar filtros, use o formato esperado."
)


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/relatorio-customizado/exportar", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def exportar_relatorio_customizado_route(request: Request, usuario: dict) -> Response:
        """Mesma consulta da rota acima, mas devolvendo um arquivo Excel (.xlsx) para download."""
        parametros = parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": _ERRO_PARAMETROS}, status_code=400, headers=CORS_HEADERS)

        try:
            colunas, linhas = buscar_relatorio_customizado(*parametros)
        except RelatorioCustomizadoInvalido as erro:
            return JSONResponse({"erro": str(erro)}, status_code=400, headers=CORS_HEADERS)

        _comum.registrar_acesso(usuario, "relatorio_customizado:exportar", len(linhas))
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Relatório Customizado")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="relatorio_customizado.xlsx"',
                **CORS_HEADERS,
            },
        )

    @mcp.custom_route("/api/financeiro/relatorio-customizado", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def gerar_relatorio_customizado_route(request: Request, usuario: dict) -> JSONResponse:
        """Monta e executa o SELECT (com JOINs resolvidos automaticamente) para as colunas/filial escolhidas na tela "Criar Relatório"."""
        parametros = parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": _ERRO_PARAMETROS}, status_code=400, headers=CORS_HEADERS)

        try:
            colunas, linhas = buscar_relatorio_customizado(*parametros)
        except RelatorioCustomizadoInvalido as erro:
            return JSONResponse({"erro": str(erro)}, status_code=400, headers=CORS_HEADERS)

        _comum.registrar_acesso(usuario, "relatorio_customizado:listar", len(linhas))
        dados = [
            dict(zip(colunas, (_comum.serializar(valor) for valor in linha), strict=True)) for linha in linhas
        ]
        return JSONResponse(dados, headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/relatorio/opcoes-coluna", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def listar_opcoes_coluna_route(request: Request, usuario: dict) -> JSONResponse:
        """Valores distintos de uma coluna do tipo "texto" (formato view.coluna) — usado pra popular o select multiplo do filtro dessa coluna."""
        token = request.query_params.get("coluna", "").strip()
        validado = validar_coluna(token)
        if validado is None:
            return JSONResponse(
                {"erro": "Informe uma coluna válida (formato view.coluna)."},
                status_code=400,
                headers=CORS_HEADERS,
            )

        nome_view, nome_coluna = validado
        if inferir_tipo_filtro(nome_coluna) != "texto":
            return JSONResponse(
                {"erro": "Essa coluna não tem filtro por lista de valores."},
                status_code=400,
                headers=CORS_HEADERS,
            )

        valores = buscar_opcoes_coluna(nome_view, nome_coluna)
        return JSONResponse([{"valor": valor, "rotulo": valor} for valor in valores], headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/relatorio/views", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def listar_views_route(request: Request, usuario: dict) -> JSONResponse:
        """Lista as views financeiras liberadas, suas colunas e relacionamentos — usado pela tela "Criar Relatório" pra montar a lista de tabelas.

        "filial" fica de fora das colunas de cada view: toda view liberada tem
        essa coluna e ela já é filtro obrigatório aplicado globalmente (seletor
        único no topo da tela, resolvido em `_montar_sql`) — oferecê-la também
        como coluna marcável em cada view deixava o usuário marcar "filial" em
        views diferentes e o relatório final saía com várias colunas "filial"
        idênticas. `schema.py` continua com a coluna (a IA do chat e o filtro
        automático de `_montar_sql` dependem dela) — só esta rota, que alimenta
        especificamente esse checklist, tira ela da lista."""
        payload = [
            {
                "nome": view.nome,
                "descricao": view.descricao,
                "colunas": [
                    {
                        "nome": coluna.nome,
                        "descricao": coluna.descricao,
                        "tipo": inferir_tipo_filtro(coluna.nome),
                    }
                    for coluna in view.colunas
                    if coluna.nome != "filial"
                ],
                "relacionamentos": [
                    {
                        "viewDestino": rel.view_destino,
                        "colunasLocais": list(rel.colunas_locais),
                        "colunasDestino": list(rel.colunas_destino),
                        "descricao": rel.descricao,
                    }
                    for rel in view.relacionamentos
                ],
            }
            for view in VIEWS_DISPONIVEIS
        ]
        return JSONResponse(payload, headers=CORS_HEADERS)
