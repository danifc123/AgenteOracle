"""Rotas HTTP do construtor de relatório sob demanda para a tela "Criar
Relatório": o usuário escolhe colunas de uma ou mais views financeiras
liberadas (`agent/financeiro/schema.py` — o mesmo registro que a IA usa em
`consulta_livre`) e monta um relatório com os JOINs resolvidos
automaticamente pelos relacionamentos declarados entre as views. A lógica de
validação/montagem de SQL em si mora em `relatorio_customizado_sql.py` — este
módulo só cuida do HTTP (parsing de request, status code, resposta), mesmo
padrão dos outros relatórios fixos deste pacote (ex: `desvio_margem.py`,
`duplicata_mercantil.py`: `_parametros_da_query` privada aqui, `registrar`
por último)."""

import json

from anyio import to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.financeiro.schema import VIEWS_DISPONIVEIS, inferir_tipo_filtro
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.relatorio_customizado_sql import (
    RelatorioCustomizadoInvalido,
    ViewIndisponivel,
    buscar_opcoes_colunas,
    buscar_relatorio_customizado,
    rotular_opcao,
    suporta_lista_opcoes,
    validar_coluna,
)

_CAMPOS_FILTRO_ACEITOS = {"valores", "min", "max", "ini", "fim"}

_ERRO_PARAMETROS = (
    "Informe ao menos uma filial e uma coluna válida (formato view.coluna) — "
    "e, se enviar filtros, use o formato esperado."
)

_ERRO_EXPORTAR_LINHAS = (
    'Informe "colunas" (lista de nomes) e "linhas" (lista de listas, cada uma do mesmo tamanho de colunas).'
)


def _corpo_exportar_linhas_valido(corpo: object) -> tuple[list[str], list[list]] | None:
    if not isinstance(corpo, dict):
        return None
    colunas = corpo.get("colunas")
    linhas = corpo.get("linhas")
    if not isinstance(colunas, list) or not colunas or not all(isinstance(c, str) for c in colunas):
        return None
    if not isinstance(linhas, list) or not all(
        isinstance(linha, list) and len(linha) == len(colunas) for linha in linhas
    ):
        return None
    return colunas, linhas


def _gerar_xlsx_relatorio_customizado(colunas: list[str], linhas: list[list]) -> Response:
    conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Relatório Customizado")
    return Response(
        content=conteudo_xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="relatorio_customizado.xlsx"',
            **CORS_HEADERS,
        },
    )


def _opcoes_da_coluna(chave: str, valores: list[str]) -> list[dict[str, str]]:
    """`valor` é sempre o cru (é o que volta no filtro); `rotulo` é o texto
    legível. Quando algum valor ganhou rótulo, a lista sai ordenada por ele —
    a ordem do banco (pelo código cru) não faz sentido pra quem lê "CIF",
    "FOB"..."""
    nome_view, _, nome_coluna = chave.partition(".")
    opcoes = [{"valor": valor, "rotulo": rotular_opcao(nome_view, nome_coluna, valor)} for valor in valores]
    if any(opcao["valor"] != opcao["rotulo"] for opcao in opcoes):
        opcoes.sort(key=lambda opcao: opcao["rotulo"].casefold())
    return opcoes


def _parametros_da_query(
    request: Request,
) -> tuple[dict[str, list[str]], list[str], dict[str, dict[str, str | list[str]]], int] | None:
    """Lê `filial` (obrigatório), `colunas` (obrigatório, formato
    "view.coluna,view.coluna,...") `filtros` (opcional) e `pagina` (opcional,
    default 1) — devolve (colunas_por_view, filiais, filtros, pagina) já
    validados contra o registro de views, ou None se algo essencial faltar/
    for inválido."""
    filial_bruto = request.query_params.get("filial", "").strip()
    filiais = [item.strip() for item in filial_bruto.split(",") if item.strip()]

    colunas_bruto = request.query_params.get("colunas", "").strip()
    if not filiais or not colunas_bruto:
        return None

    colunas_por_view: dict[str, list[str]] = {}
    for token in colunas_bruto.split(","):
        validado = validar_coluna(token.strip())
        if validado is None:
            return None
        nome_view, nome_coluna = validado
        colunas_por_view.setdefault(nome_view, [])
        if nome_coluna not in colunas_por_view[nome_view]:
            colunas_por_view[nome_view].append(nome_coluna)

    if not colunas_por_view:
        return None

    filtros = _parametros_filtros(request)
    if filtros is None:
        return None

    pagina_bruto = request.query_params.get("pagina", "1").strip()
    pagina = int(pagina_bruto) if pagina_bruto.isdigit() else 1
    pagina = max(pagina, 1)

    return colunas_por_view, filiais, filtros, pagina


def _parametros_filtros(request: Request) -> dict[str, dict[str, str | list[str]]] | None:
    """Lê `filtros` (opcional, JSON: {"view.coluna": {"valores"|"min"|"max"|"ini"|"fim": ...}}
    — "valores" é sempre uma lista, os demais são string) e devolve só as
    entradas com coluna válida e algum valor não vazio — ignora
    silenciosamente chaves de filtro que o tipo da coluna não usa (quem
    decide que campos valem pra cada coluna é sempre `_montar_sql` de
    `relatorio_customizado_sql.py`, via `inferir_tipo_filtro`, nunca o que
    vier daqui)."""
    bruto = request.query_params.get("filtros", "").strip()
    if not bruto:
        return {}

    try:
        dados = json.loads(bruto)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(dados, dict):
        return None

    filtros: dict[str, dict[str, str | list[str]]] = {}
    for chave, valor in dados.items():
        if validar_coluna(chave) is None or not isinstance(valor, dict):
            return None

        entrada: dict[str, str | list[str]] = {}
        for campo, conteudo in valor.items():
            if campo not in _CAMPOS_FILTRO_ACEITOS:
                continue
            if campo == "valores":
                if not isinstance(conteudo, list):
                    return None
                limpos = [str(item).strip() for item in conteudo if str(item).strip()]
                if limpos:
                    entrada["valores"] = limpos
            elif str(conteudo).strip():
                entrada[campo] = str(conteudo).strip()

        if entrada:
            filtros[chave] = entrada

    return filtros


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/relatorio-customizado/exportar-linhas", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def exportar_linhas_relatorio_customizado_route(request: Request, usuario: dict) -> Response:
        """Gera o .xlsx a partir das linhas que a tela MANDA no corpo — não
        reconsulta o banco. `relatorioDados` no frontend acumula todas as
        páginas já trazidas por "Carregar mais", então baixar exporta
        exatamente o que está visível na tela (não só a 1ª página de 1000
        linhas, como a versão antiga desta rota fazia reconsultando do
        zero). Só o parsing do corpo é assíncrono de verdade (`request.json()`);
        montar a planilha (`gerar_xlsx`, síncrono/CPU-bound) roda em thread
        separada, mesmo padrão de `login_route`."""
        corpo_valido = _corpo_exportar_linhas_valido(await request.json())
        if corpo_valido is None:
            return JSONResponse({"erro": _ERRO_EXPORTAR_LINHAS}, status_code=400, headers=CORS_HEADERS)

        colunas, linhas = corpo_valido
        _comum.registrar_acesso(usuario, "relatorio_customizado:exportar", len(linhas))
        return await to_thread.run_sync(_gerar_xlsx_relatorio_customizado, colunas, linhas)

    @mcp.custom_route("/api/financeiro/relatorio-customizado", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    def gerar_relatorio_customizado_route(request: Request, usuario: dict) -> JSONResponse:
        """Monta e executa o SELECT (com JOINs resolvidos automaticamente) para as colunas/filial escolhidas na tela "Criar Relatório"."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": _ERRO_PARAMETROS}, status_code=400, headers=CORS_HEADERS)

        try:
            colunas, linhas, tem_mais_paginas = buscar_relatorio_customizado(*parametros)
        except ViewIndisponivel as erro:
            return JSONResponse({"erro": str(erro)}, status_code=503, headers=CORS_HEADERS)
        except RelatorioCustomizadoInvalido as erro:
            return JSONResponse({"erro": str(erro)}, status_code=400, headers=CORS_HEADERS)

        _comum.registrar_acesso(usuario, "relatorio_customizado:listar", len(linhas))
        dados = [
            dict(zip(colunas, (_comum.serializar(valor) for valor in linha), strict=True)) for linha in linhas
        ]
        headers = {**CORS_HEADERS, "X-Tem-Mais-Paginas": "true" if tem_mais_paginas else "false"}
        return JSONResponse(dados, headers=headers)

    @mcp.custom_route("/api/financeiro/relatorio/opcoes-coluna", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    def listar_opcoes_coluna_route(request: Request, usuario: dict) -> JSONResponse:
        """Valores distintos de uma ou mais colunas do tipo "texto"/
        "texto-numerico" (formato "view.coluna,view.coluna,...") — usado
        pra popular o select múltiplo do filtro dessas colunas na tela,
        numa requisição só em vez de uma por coluna."""
        colunas_bruto = request.query_params.get("colunas", "").strip()
        if not colunas_bruto:
            return JSONResponse(
                {"erro": "Informe ao menos uma coluna válida (formato view.coluna)."},
                status_code=400,
                headers=CORS_HEADERS,
            )

        colunas_validas: list[tuple[str, str]] = []
        for token in colunas_bruto.split(","):
            validado = validar_coluna(token.strip())
            if validado is None:
                return JSONResponse(
                    {"erro": "Informe apenas colunas válidas (formato view.coluna)."},
                    status_code=400,
                    headers=CORS_HEADERS,
                )
            nome_view, nome_coluna = validado
            if not suporta_lista_opcoes(nome_view, nome_coluna):
                return JSONResponse(
                    {"erro": f"A coluna '{nome_view}.{nome_coluna}' não tem filtro por lista de valores."},
                    status_code=400,
                    headers=CORS_HEADERS,
                )
            colunas_validas.append((nome_view, nome_coluna))

        try:
            valores_por_coluna = buscar_opcoes_colunas(colunas_validas)
        except ViewIndisponivel as erro:
            return JSONResponse({"erro": str(erro)}, status_code=503, headers=CORS_HEADERS)
        payload = {chave: _opcoes_da_coluna(chave, valores) for chave, valores in valores_por_coluna.items()}
        return JSONResponse(payload, headers=CORS_HEADERS)

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
                "fonte": view.fonte,
                "colunas": [
                    {
                        "nome": coluna.nome,
                        "descricao": coluna.descricao,
                        "tipo": inferir_tipo_filtro(coluna),
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
