"""Lógica pura (sem HTTP, sem I/O exceto a consulta em si) do relatório
customizado: validação de coluna, montagem do SELECT com JOINs resolvidos
automaticamente pelo grafo de relacionamentos das views, e execução da
consulta. Separado de `relatorio_customizado.py` (que cuida das rotas HTTP,
incluindo o parsing de query params em `parametros_da_query`) pra ficar
testável isoladamente, sem precisar de um `Request` do Starlette pra
exercitar a parte que realmente tem lógica de negócio.

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

from collections import deque

from agente_oracle.agent.financeiro.schema import (
    VIEWS_DISPONIVEIS,
    ColunaView,
    ViewFinanceira,
    inferir_tipo_filtro,
)
from agente_oracle.db.connection import get_connection_para_fonte
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

LIMITE_MAXIMO_LINHAS = 1000
LIMITE_OPCOES_COLUNA = 500

_VIEWS_POR_NOME: dict[str, ViewFinanceira] = {view.nome: view for view in VIEWS_DISPONIVEIS}


class RelatorioCustomizadoInvalido(Exception):
    """Levantada quando a seleção de colunas/filtros pedida pela tela não pode virar um SQL válido."""


def _coluna_view(nome_view: str, nome_coluna: str) -> ColunaView:
    """Resolve o `ColunaView` (com `tipo_filtro`, se declarado) a partir de
    um par nome_view/nome_coluna já validado contra o registro — usado
    pelos pontos que precisam chamar `inferir_tipo_filtro`."""
    view = _VIEWS_POR_NOME[nome_view]
    return next(coluna for coluna in view.colunas if coluna.nome == nome_coluna)


def buscar_opcoes_coluna(nome_view: str, nome_coluna: str) -> list[str]:
    """Valores distintos (não nulos) de uma coluna do tipo "texto" ou
    "texto-numerico" — usado pra popular o <select multiplo> do filtro
    dessa coluna na tela. `nome_view` e `nome_coluna` já vêm validados
    contra o registro (nunca texto cru do cliente), então é seguro
    interpolar direto no SQL."""
    sql = (
        f'SELECT DISTINCT "{nome_coluna}" FROM {nome_view} '
        f'WHERE "{nome_coluna}" IS NOT NULL '
        f'ORDER BY "{nome_coluna}" '
        f"FETCH FIRST {LIMITE_OPCOES_COLUNA} ROWS ONLY"
    )
    with get_connection_para_fonte(_VIEWS_POR_NOME[nome_view].fonte) as connection:
        cursor = connection.cursor()
        cursor.execute(sql)
        return [str(linha[0]) for linha in cursor.fetchall()]


def suporta_lista_opcoes(nome_view: str, nome_coluna: str) -> bool:
    """A coluna (já validada) tem filtro por lista de valores exatos —
    "texto" ou "texto-numerico" — e por isso pode alimentar
    `buscar_opcoes_coluna`/`buscar_opcoes_colunas`? Usado por
    `listar_opcoes_coluna_route` pra rejeitar colunas do tipo "numero"/
    "periodo-data", que não têm esse modo de filtro."""
    return inferir_tipo_filtro(_coluna_view(nome_view, nome_coluna)) in ("texto", "texto-numerico")


def buscar_opcoes_colunas(colunas: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Mesma consulta de `buscar_opcoes_coluna`, mas pra várias colunas de
    uma vez — ainda um `SELECT DISTINCT` por coluna internamente (não dá
    pra combinar num `SELECT` só, cada coluna tem sua própria lista de
    distintos), mas numa chamada/thread só em vez de uma requisição HTTP
    por coluna. `colunas` já vem validada; devolve um dict chaveado por
    "view.coluna", no mesmo formato de `filtros` em `_montar_sql`."""
    return {
        f"{nome_view}.{nome_coluna}": buscar_opcoes_coluna(nome_view, nome_coluna)
        for nome_view, nome_coluna in colunas
    }


def buscar_relatorio_customizado(
    colunas_por_view: dict[str, list[str]],
    filiais: list[str],
    filtros: dict[str, dict[str, str | list[str]]],
    pagina: int,
) -> tuple[list[str], list[tuple], bool]:
    fonte = _fonte_comum(list(colunas_por_view.keys()))
    offset = (pagina - 1) * LIMITE_MAXIMO_LINHAS
    sql, binds = _montar_sql(colunas_por_view, filiais, filtros, offset)

    with get_connection_para_fonte(fonte) as connection:
        cursor = connection.cursor()
        cursor.execute(sql, **binds)
        colunas = [descricao[0] for descricao in cursor.description]
        linhas = cursor.fetchall()

    # Pede uma linha a mais que o necessário (ver `_montar_sql`) só pra saber
    # se existe próxima página sem precisar de um `COUNT(*)` — que seria caro
    # nas views com CTE pesada (ex: `vwia_baixas_pagar`) pelo mesmo motivo que
    # a consulta principal já é.
    tem_mais_paginas = len(linhas) > LIMITE_MAXIMO_LINHAS
    return colunas, linhas[:LIMITE_MAXIMO_LINHAS], tem_mais_paginas


def _fonte_comum(views_selecionadas: list[str]) -> str:
    """Todas as views escolhidas precisam vir da mesma fonte: STAGE e
    Protheus são instâncias Oracle separadas, sem `DB LINK` entre elas, então
    não existe SQL único capaz de fazer JOIN entre uma view de cada lado.
    Levanta `RelatorioCustomizadoInvalido` com uma mensagem específica pra
    esse caso — sem essa checagem, a combinação ainda falharia lá na frente
    (nenhuma view declara relacionamento pra uma view de outra fonte), mas
    com o erro genérico de "sem caminho de JOIN" do BFS, que não deixa claro
    o motivo real."""
    fontes = {_VIEWS_POR_NOME[nome].fonte for nome in views_selecionadas}
    if len(fontes) > 1:
        raise RelatorioCustomizadoInvalido(
            "Não é possível combinar views de fontes diferentes (STAGE e Protheus) no mesmo relatório."
        )
    return fontes.pop()


def _montar_sql(
    colunas_por_view: dict[str, list[str]],
    filiais: list[str],
    filtros: dict[str, dict[str, str | list[str]]],
    offset: int,
) -> tuple[str, dict[str, str | int]]:
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

    binds: dict[str, str | int] = {}
    condicoes_where = []
    for nome_view in colunas_por_view:
        view = _VIEWS_POR_NOME[nome_view]
        if not any(coluna.nome == "filial" for coluna in view.colunas):
            continue
        alias = alias_por_view[nome_view]
        marcadores, binds_filial = clausula_in(f"filial_{alias}", filiais)
        binds.update(binds_filial)
        clausula = f'{alias}."filial" IN {marcadores}'
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
        coluna_declarada = _coluna_view(nome_view, nome_coluna)
        tipo = inferir_tipo_filtro(coluna_declarada)

        if tipo == "periodo-data":
            # A maioria das colunas "data_*" já é DATE de verdade na view (não
            # texto "YYYYMMDD" cru do Protheus, como nos relatórios fixos) —
            # só o bind, que chega da tela como "YYYY-MM-DD" (`<input
            # type="date">`), precisa converter. Só as colunas ainda
            # guardadas como texto formatado (`formato_data_texto` declarado
            # em schema.py, ex: várias datas das views VWIA_*) precisam do
            # `TO_DATE` no lado da coluna também.
            coluna_data = (
                coluna_sql
                if coluna_declarada.formato_data_texto is None
                else f"TO_DATE({coluna_sql}, '{coluna_declarada.formato_data_texto}')"
            )
            for extremo, operador in (("ini", ">="), ("fim", "<=")):
                if not filtro.get(extremo):
                    continue
                contador_filtro += 1
                bind = f"filtro_{contador_filtro}"
                binds[bind] = filtro[extremo]
                condicoes_where.append(f"{coluna_data} {operador} TO_DATE(:{bind}, 'YYYY-MM-DD')")
            continue

        # "texto-numerico" (ex: coluna "nota") aceita os dois filtros ao
        # mesmo tempo — a tela deixa o usuário alternar entre lista e
        # faixa pra essa coluna, mas o backend não presume qual dos dois
        # veio preenchido, só aplica o que tiver valor.
        if tipo in ("numero", "texto-numerico"):
            # "numero" já é NUMBER de verdade na view; "texto-numerico" é
            # texto zero-padded ("000000002") que precisa virar número
            # antes de comparar com a faixa.
            coluna_numerica = coluna_sql if tipo == "numero" else _comum.numero_coluna(coluna_sql)
            for extremo, operador in (("min", ">="), ("max", "<=")):
                if not filtro.get(extremo):
                    continue
                contador_filtro += 1
                bind = f"filtro_{contador_filtro}"
                binds[bind] = filtro[extremo]
                condicoes_where.append(f"{coluna_numerica} {operador} {_comum.numero_bind(bind)}")

        if tipo in ("texto", "texto-numerico"):
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

    # Pede uma linha a mais que `LIMITE_MAXIMO_LINHAS` (ver `buscar_relatorio_customizado`,
    # que descarta essa linha extra) só pra saber se tem próxima página sem
    # precisar de um `COUNT(*)` separado. `OFFSET ... FETCH NEXT ...` é ANSI
    # SQL — funciona em Oracle e Postgres sem branch por `db_backend`, igual
    # o `FETCH FIRST` que já existia aqui antes da paginação.
    sql.append("OFFSET :pagina_offset ROWS FETCH NEXT :pagina_limite ROWS ONLY")
    binds["pagina_offset"] = offset
    binds["pagina_limite"] = LIMITE_MAXIMO_LINHAS + 1

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
