"""Lógica pura (sem HTTP, sem I/O exceto a consulta em si) do relatório
customizado: validação de coluna, montagem do SELECT com JOINs resolvidos
automaticamente pelo grafo de relacionamentos das views, e execução da
consulta. Separado de `relatorio_customizado.py` (que só cuida das rotas
HTTP) pra ficar testável isoladamente, sem precisar de um `Request` do
Starlette pra exercitar a parte que realmente tem lógica de negócio.

Diferente de `consulta_livre` (que valida um SQL gerado pela IA), aqui o SQL
inteiro é montado a partir de nomes já validados contra o registro
(`agent/financeiro/schema.py`) — não existe concatenação de texto vindo do
usuário em posição de identificador, então não há risco de injeção por esse
caminho.

Filtro de filial é obrigatório e sempre aplicado a toda view selecionada que
tenha uma coluna "filial". Além disso, cada coluna selecionada pode ganhar um
filtro próprio — o tipo (texto/número/período de data) é sempre decidido por
`inferir_tipo_filtro` (nunca pelo que o cliente mandar), então não tem como o
front pedir uma cláusula incompatível com a coluna real.

Filtro de coluna do tipo "texto" é sempre por lista de valores exatos (como a
tela pede os valores de um <select multiplo> preenchido com os valores
distintos que já existem naquela coluna — ver `buscar_opcoes_coluna` — não
com texto livre digitado pelo usuário)."""

import json
from collections import deque

from starlette.requests import Request

from agente_oracle.agent.financeiro.schema import VIEWS_DISPONIVEIS, ViewFinanceira, inferir_tipo_filtro
from agente_oracle.db.connection import get_connection
from agente_oracle.server.financeiro.relatorios import _comum

LIMITE_MAXIMO_LINHAS = 1000
LIMITE_OPCOES_COLUNA = 500

_CAMPOS_FILTRO_ACEITOS = {"valores", "min", "max", "ini", "fim"}

_VIEWS_POR_NOME: dict[str, ViewFinanceira] = {view.nome: view for view in VIEWS_DISPONIVEIS}


class RelatorioCustomizadoInvalido(Exception):
    """Levantada quando a seleção de colunas/filtros pedida pela tela não pode virar um SQL válido."""


def buscar_opcoes_coluna(nome_view: str, nome_coluna: str) -> list[str]:
    """Valores distintos (não nulos) de uma coluna de tipo "texto" — usado
    pra popular o <select multiplo> do filtro dessa coluna na tela. `nome_view`
    e `nome_coluna` já vêm validados contra o registro (nunca texto cru do
    cliente), então é seguro interpolar direto no SQL."""
    sql = (
        f'SELECT DISTINCT "{nome_coluna}" FROM {nome_view} '
        f'WHERE "{nome_coluna}" IS NOT NULL '
        f'ORDER BY "{nome_coluna}" '
        f"FETCH FIRST {LIMITE_OPCOES_COLUNA} ROWS ONLY"
    )
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql)
        return [str(linha[0]) for linha in cursor.fetchall()]


def buscar_relatorio_customizado(
    colunas_por_view: dict[str, list[str]], filiais: list[str], filtros: dict[str, dict[str, str | list[str]]]
) -> tuple[list[str], list[tuple]]:
    sql, binds = _montar_sql(colunas_por_view, filiais, filtros)

    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, **binds)
        colunas = [descricao[0] for descricao in cursor.description]
        linhas = cursor.fetchall()
    return colunas, linhas


def _montar_sql(
    colunas_por_view: dict[str, list[str]], filiais: list[str], filtros: dict[str, dict[str, str | list[str]]]
) -> tuple[str, dict[str, str]]:
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
            for col_pai, col_filha in zip(cols_pai, cols_filha, strict=True)
        )
        sql.append(f"LEFT JOIN {view_filha} {alias_filha} ON {condicoes}")

    binds: dict[str, str] = {}
    condicoes_where = []
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
        condicoes_where.append(clausula)

    contador_filtro = 0
    for chave_filtro, filtro in filtros.items():
        nome_view, _, nome_coluna = chave_filtro.partition(".")
        if nome_view not in alias_por_view:
            continue  # coluna de uma view que nem entrou no relatório atual

        alias = alias_por_view[nome_view]
        coluna_sql = f'{alias}."{nome_coluna}"'
        tipo = inferir_tipo_filtro(nome_coluna)

        if tipo == "periodo-data":
            # `coluna_sql` já é DATE de verdade na view (não texto "YYYYMMDD" cru
            # do Protheus, como nos relatórios fixos) — só o bind, que chega da
            # tela como "YYYY-MM-DD" (`<input type="date">`), precisa converter.
            for extremo, operador in (("ini", ">="), ("fim", "<=")):
                if not filtro.get(extremo):
                    continue
                contador_filtro += 1
                bind = f"filtro_{contador_filtro}"
                binds[bind] = filtro[extremo]
                condicoes_where.append(f"{coluna_sql} {operador} TO_DATE(:{bind}, 'YYYY-MM-DD')")
        elif tipo == "numero":
            for extremo, operador in (("min", ">="), ("max", "<=")):
                if not filtro.get(extremo):
                    continue
                contador_filtro += 1
                bind = f"filtro_{contador_filtro}"
                binds[bind] = filtro[extremo]
                condicoes_where.append(f"{coluna_sql} {operador} {_comum.numero_bind(bind)}")
        else:
            valores_filtro = filtro.get("valores")
            if valores_filtro:
                marcadores = []
                for item in valores_filtro:
                    contador_filtro += 1
                    bind = f"filtro_{contador_filtro}"
                    binds[bind] = item
                    marcadores.append(f":{bind}")
                condicoes_where.append(f"{_comum.texto_coluna(coluna_sql)} IN ({', '.join(marcadores)})")

    if condicoes_where:
        sql.append(f"WHERE {' AND '.join(condicoes_where)}")

    sql.append(f"FETCH FIRST {LIMITE_MAXIMO_LINHAS} ROWS ONLY")

    return "\n".join(sql), binds


def _resolver_caminho_join(
    views_selecionadas: list[str],
) -> list[tuple[str, str, tuple[str, ...], tuple[str, ...]]]:
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


def parametros_da_query(
    request: Request,
) -> tuple[dict[str, list[str]], list[str], dict[str, dict[str, str | list[str]]]] | None:
    """Lê `filial` (obrigatório), `colunas` (obrigatório, formato
    "view.coluna,view.coluna,...") e `filtros` (opcional) — devolve
    (colunas_por_view, filiais, filtros) já validados contra o registro de
    views, ou None se algo essencial faltar/for inválido."""
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

    return colunas_por_view, filiais, filtros


def _parametros_filtros(request: Request) -> dict[str, dict[str, str | list[str]]] | None:
    """Lê `filtros` (opcional, JSON: {"view.coluna": {"valores"|"min"|"max"|"ini"|"fim": ...}}
    — "valores" é sempre uma lista, os demais são string) e devolve só as
    entradas com coluna válida e algum valor não vazio — ignora
    silenciosamente chaves de filtro que o tipo da coluna não usa (quem
    decide que campos valem pra cada coluna é sempre `_montar_sql`, via
    `inferir_tipo_filtro`, nunca o que vier daqui)."""
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


def validar_coluna(token: str) -> tuple[str, str] | None:
    """Confere que `token` (formato "view.coluna") existe no registro —
    devolve (nome_view, nome_coluna) ou None se inválido."""
    if "." not in token:
        return None
    nome_view, _, nome_coluna = token.partition(".")
    view = _VIEWS_POR_NOME.get(nome_view)
    if view is None or nome_coluna not in {coluna.nome for coluna in view.colunas}:
        return None
    return nome_view, nome_coluna
