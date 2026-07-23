"""Construtor de relatório sob demanda para a tela "Criar Relatório": o
usuário escolhe colunas de uma ou mais views financeiras liberadas
(`agent/financeiro/schema.py` — o mesmo registro que a IA usa em
`consulta_livre`) e este módulo monta o SELECT com os JOINs necessários,
usando os relacionamentos declarados entre as views.

Diferente de `consulta_livre` (que valida um SQL gerado pela IA), aqui o SQL
inteiro é montado no servidor a partir de nomes já validados contra o
registro — não existe concatenação de texto vindo do usuário em posição de
identificador, então não há risco de injeção por esse caminho.

MVP: filtro único de filial (obrigatório) aplicado a toda view selecionada
que tenha uma coluna "filial". Filtros adicionais por coluna (período,
texto) ficam para uma iteração futura.
"""

from collections import deque
from decimal import Decimal

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.financeiro.schema import VIEWS_DISPONIVEIS, ViewFinanceira
from agente_oracle.db.connection import get_connection
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.auth.dependencia import exigir_usuario
from agente_oracle.server.cors import CORS_HEADERS, resposta_preflight

LIMITE_MAXIMO_LINHAS = 1000

_VIEWS_POR_NOME: dict[str, ViewFinanceira] = {view.nome: view for view in VIEWS_DISPONIVEIS}


class RelatorioCustomizadoInvalido(Exception):
    """Levantada quando a seleção de colunas/filtros pedida pela tela não pode virar um SQL válido."""


def _grafo_relacionamentos() -> dict[str, list[tuple[str, tuple[str, ...], tuple[str, ...]]]]:
    """Monta o grafo de relacionamentos entre views nos dois sentidos (a
    declaração no schema é de mão única, mas o JOIN vale nos dois lados)."""
    grafo: dict[str, list[tuple[str, tuple[str, ...], tuple[str, ...]]]] = {
        view.nome: [] for view in VIEWS_DISPONIVEIS
    }
    for view in VIEWS_DISPONIVEIS:
        for rel in view.relacionamentos:
            grafo[view.nome].append((rel.view_destino, rel.colunas_locais, rel.colunas_destino))
            grafo[rel.view_destino].append((view.nome, rel.colunas_destino, rel.colunas_locais))
    return grafo


def _resolver_caminho_join(views_selecionadas: list[str]) -> list[tuple[str, str, tuple[str, ...], tuple[str, ...]]]:
    """BFS a partir da primeira view selecionada (raiz) — devolve a lista de
    arestas (view_pai, view_filha, colunas_pai, colunas_filha) necessárias
    pra conectar todas as views selecionadas à raiz. Levanta
    RelatorioCustomizadoInvalido se alguma view selecionada não tiver
    caminho até a raiz pelos relacionamentos declarados."""
    grafo = _grafo_relacionamentos()
    raiz = views_selecionadas[0]

    visitado = {raiz}
    ordem_descoberta = [raiz]
    pai: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {}
    fila = deque([raiz])

    while fila:
        atual = fila.popleft()
        for destino, cols_locais, cols_destino in grafo.get(atual, []):
            if destino in visitado:
                continue
            visitado.add(destino)
            ordem_descoberta.append(destino)
            pai[destino] = (atual, cols_locais, cols_destino)
            fila.append(destino)

    faltando = [v for v in views_selecionadas if v not in visitado]
    if faltando:
        raise RelatorioCustomizadoInvalido(
            f"Não é possível combinar {', '.join(faltando)} com '{raiz}': não existe relacionamento "
            "direto ou indireto declarado entre essas tabelas."
        )

    necessarias = {raiz}
    for view in views_selecionadas:
        atual = view
        while atual != raiz:
            necessarias.add(atual)
            atual = pai[atual][0]

    arestas: list[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = []
    for view in ordem_descoberta:
        if view == raiz or view not in necessarias:
            continue
        view_pai, cols_pai, cols_filha = pai[view]
        arestas.append((view_pai, view, cols_pai, cols_filha))

    return arestas


def _parametros_da_query(request: Request) -> tuple[dict[str, list[str]], list[str]] | None:
    """Lê `filial` (obrigatório) e `colunas` (obrigatório, formato
    "view.coluna,view.coluna,...") e devolve (colunas_por_view, filiais)
    já validados contra o registro de views — ou None se algo essencial
    faltar/for inválido."""
    filial_bruto = request.query_params.get("filial", "").strip()
    filiais = [item.strip() for item in filial_bruto.split(",") if item.strip()]

    colunas_bruto = request.query_params.get("colunas", "").strip()
    if not filiais or not colunas_bruto:
        return None

    colunas_por_view: dict[str, list[str]] = {}
    for token in colunas_bruto.split(","):
        token = token.strip()
        if "." not in token:
            return None
        nome_view, _, nome_coluna = token.partition(".")
        view = _VIEWS_POR_NOME.get(nome_view)
        if view is None or nome_coluna not in {coluna.nome for coluna in view.colunas}:
            return None
        colunas_por_view.setdefault(nome_view, [])
        if nome_coluna not in colunas_por_view[nome_view]:
            colunas_por_view[nome_view].append(nome_coluna)

    if not colunas_por_view:
        return None

    return colunas_por_view, filiais


def _montar_sql(colunas_por_view: dict[str, list[str]], filiais: list[str]) -> tuple[str, dict[str, str]]:
    views_selecionadas = list(colunas_por_view.keys())
    arestas = _resolver_caminho_join(views_selecionadas)

    raiz = views_selecionadas[0]
    # `arestas` vem em ordem de descoberta do BFS (pai sempre antes do filho),
    # então cada view não-raiz aparece como "filha" de uma aresta exatamente uma
    # vez — inclui de quebra as views que entraram só como "escala" no caminho.
    alias_por_view: dict[str, str] = {raiz: "v0"}
    for indice, (_pai, filha, _cl, _cd) in enumerate(arestas, start=1):
        alias_por_view[filha] = f"v{indice}"
    partes_select = []
    for nome_view, colunas in colunas_por_view.items():
        alias = alias_por_view[nome_view]
        for coluna in colunas:
            rotulo = f"{nome_view}.{coluna}"
            partes_select.append(f'{alias}."{coluna}" AS "{rotulo}"')

    sql = [f"SELECT {', '.join(partes_select)}", f"FROM {raiz} {alias_por_view[raiz]}"]

    for view_pai, view_filha, cols_pai, cols_filha in arestas:
        alias_pai = alias_por_view[view_pai]
        alias_filha = alias_por_view[view_filha]
        condicoes = " AND ".join(
            f'{alias_pai}."{col_pai}" = {alias_filha}."{col_filha}"'
            for col_pai, col_filha in zip(cols_pai, cols_filha)
        )
        sql.append(f"LEFT JOIN {view_filha} {alias_filha} ON {condicoes}")

    binds: dict[str, str] = {}
    condicoes_filial = []
    for nome_view in colunas_por_view:
        view = _VIEWS_POR_NOME[nome_view]
        if not any(coluna.nome == "filial" for coluna in view.colunas):
            continue
        alias = alias_por_view[nome_view]
        marcadores = []
        for indice, valor in enumerate(filiais):
            chave = f"filial_{alias}_{indice}"
            binds[chave] = valor
            marcadores.append(f":{chave}")
        clausula = f'{alias}."filial" IN ({", ".join(marcadores)})'
        if nome_view != raiz:
            clausula = f'({clausula} OR {alias}."filial" IS NULL)'
        condicoes_filial.append(clausula)

    if condicoes_filial:
        sql.append(f"WHERE {' AND '.join(condicoes_filial)}")

    sql.append(f"FETCH FIRST {LIMITE_MAXIMO_LINHAS} ROWS ONLY")

    return "\n".join(sql), binds


def _serializar(valor):
    return float(valor) if isinstance(valor, Decimal) else valor


def _buscar_relatorio_customizado(colunas_por_view: dict[str, list[str]], filiais: list[str]) -> tuple[list[str], list[tuple]]:
    sql, binds = _montar_sql(colunas_por_view, filiais)

    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, **binds)
        colunas = [descricao[0] for descricao in cursor.description]
        linhas = cursor.fetchall()
    return colunas, linhas


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/relatorio/views", methods=["GET", "OPTIONS"])
    async def listar_views_route(request: Request) -> JSONResponse:
        """Lista as views financeiras liberadas, suas colunas e relacionamentos — usado pela tela "Criar Relatório" pra montar a lista de tabelas."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        payload = [
            {
                "nome": view.nome,
                "descricao": view.descricao,
                "colunas": [{"nome": coluna.nome, "descricao": coluna.descricao} for coluna in view.colunas],
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

    @mcp.custom_route("/api/financeiro/relatorio-customizado", methods=["GET", "OPTIONS"])
    async def gerar_relatorio_customizado_route(request: Request) -> JSONResponse:
        """Monta e executa o SELECT (com JOINs resolvidos automaticamente) para as colunas/filial escolhidas na tela "Criar Relatório"."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial e uma coluna válida (formato view.coluna)."},
                status_code=400,
                headers=CORS_HEADERS,
            )

        try:
            colunas, linhas = _buscar_relatorio_customizado(*parametros)
        except RelatorioCustomizadoInvalido as erro:
            return JSONResponse({"erro": str(erro)}, status_code=400, headers=CORS_HEADERS)

        dados = [dict(zip(colunas, (_serializar(valor) for valor in linha))) for linha in linhas]
        return JSONResponse(dados, headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/relatorio-customizado/exportar", methods=["GET", "OPTIONS"])
    async def exportar_relatorio_customizado_route(request: Request) -> Response:
        """Mesma consulta da rota acima, mas devolvendo um arquivo Excel (.xlsx) para download."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial e uma coluna válida (formato view.coluna)."},
                status_code=400,
                headers=CORS_HEADERS,
            )

        try:
            colunas, linhas = _buscar_relatorio_customizado(*parametros)
        except RelatorioCustomizadoInvalido as erro:
            return JSONResponse({"erro": str(erro)}, status_code=400, headers=CORS_HEADERS)

        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Relatório Customizado")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="relatorio_customizado.xlsx"',
                **CORS_HEADERS,
            },
        )
