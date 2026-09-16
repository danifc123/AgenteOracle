"""Cobre a lógica pura extraída de `relatorio_customizado.py` (ver
`relatorio_customizado_sql.py`) — resolução de JOIN por BFS e validação de
coluna, sem precisar de HTTP nem de banco (`_montar_sql`/`buscar_*` que
tocam banco não entram aqui, cobertos via integração em
`tests/integration/test_relatorio_customizado.py`)."""

import pytest

from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.relatorio_customizado_sql import (
    RelatorioCustomizadoInvalido,
    _montar_sql,
    _resolver_caminho_join,
    suporta_lista_opcoes,
    validar_coluna,
)


class TestValidarColuna:
    def test_coluna_existente(self):
        assert validar_coluna("vw_clientes.codigo") == ("vw_clientes", "codigo")

    def test_sem_ponto_e_invalido(self):
        assert validar_coluna("codigo") is None

    def test_view_inexistente(self):
        assert validar_coluna("vw_nao_existe.codigo") is None

    def test_coluna_inexistente_na_view(self):
        assert validar_coluna("vw_clientes.coluna_que_nao_existe") is None


class TestResolverCaminhoJoin:
    def test_view_unica_nao_precisa_de_join(self):
        assert _resolver_caminho_join(["vw_clientes"]) == []

    def test_relacionamento_direto(self):
        arestas = _resolver_caminho_join(["vw_titulos_receber", "vw_clientes"])
        assert arestas == [("vw_titulos_receber", "vw_clientes", ("cliente_codigo",), ("codigo",))]

    def test_relacionamento_no_sentido_inverso_da_declaracao(self):
        # `vw_clientes` não declara relacionamento nenhum (é sempre o lado
        # "destino") — o grafo precisa funcionar nos dois sentidos.
        arestas = _resolver_caminho_join(["vw_clientes", "vw_titulos_receber"])
        assert arestas == [("vw_clientes", "vw_titulos_receber", ("codigo",), ("cliente_codigo",))]

    def test_caminho_indireto_por_view_intermediaria(self):
        # vw_titulos_pagar -> vw_fornecedores não tem caminho declarado até
        # vw_clientes, mas vw_faturamento conecta clientes e pedidos.
        arestas = _resolver_caminho_join(["vw_faturamento", "vw_pedidos_venda", "vw_clientes"])
        views_nas_arestas = {view for _, view, _, _ in arestas}
        assert views_nas_arestas == {"vw_pedidos_venda", "vw_clientes"}

    def test_sem_relacionamento_declarado_levanta_erro(self):
        with pytest.raises(RelatorioCustomizadoInvalido):
            _resolver_caminho_join(["vw_titulos_pagar", "vw_clientes"])


class TestSuportaListaOpcoes:
    def test_coluna_texto_suporta(self):
        assert suporta_lista_opcoes("vw_clientes", "nome") is True

    def test_coluna_texto_numerico_suporta(self):
        # "nota" tem `tipo_filtro="texto-numerico"` declarado (ver schema.py)
        # justamente pra também oferecer o modo lista, além da faixa.
        assert suporta_lista_opcoes("vwia_notas_compra", "nota") is True

    def test_coluna_numero_nao_suporta(self):
        assert suporta_lista_opcoes("vw_titulos_pagar", "valor_original") is False

    def test_coluna_periodo_data_nao_suporta(self):
        assert suporta_lista_opcoes("vw_titulos_pagar", "data_vencimento") is False


class TestMontarSqlFiltroTextoNumerico:
    """A coluna "nota" (`tipo_filtro="texto-numerico"` em schema.py) aceita
    tanto o filtro de lista exata (`valores`, igual ao tipo "texto") quanto
    o de faixa (`min`/`max`, reaproveitando `_comum.numero_coluna`/
    `numero_bind`) — os dois, cada um só entrando na cláusula WHERE se
    vier preenchido. `_montar_sql` é lógica pura (só monta string de SQL +
    binds), não precisa de conexão de banco."""

    _COLUNAS_POR_VIEW = {"vwia_notas_compra": ["nota"]}
    _FILIAIS = ["0101"]
    _COLUNA_SQL = 'v0."nota"'  # raiz única -> alias "v0" (ver _montar_sql)

    def test_so_valores_gera_clausula_de_lista(self):
        sql, binds = _montar_sql(
            self._COLUNAS_POR_VIEW,
            self._FILIAIS,
            {"vwia_notas_compra.nota": {"valores": ["000000002", "000000499"]}},
            0,
        )
        assert f"{_comum.texto_coluna(self._COLUNA_SQL)} IN (:filtro_1, :filtro_2)" in sql
        assert binds["filtro_1"] == "000000002"
        assert binds["filtro_2"] == "000000499"
        # não deve ter montado a cláusula de faixa também
        assert _comum.numero_coluna(self._COLUNA_SQL) not in sql

    def test_so_faixa_gera_clausula_numerica(self):
        sql, binds = _montar_sql(
            self._COLUNAS_POR_VIEW,
            self._FILIAIS,
            {"vwia_notas_compra.nota": {"min": "2", "max": "499"}},
            0,
        )
        coluna_numerica = _comum.numero_coluna(self._COLUNA_SQL)
        assert f"{coluna_numerica} >= {_comum.numero_bind('filtro_1')}" in sql
        assert f"{coluna_numerica} <= {_comum.numero_bind('filtro_2')}" in sql
        assert binds["filtro_1"] == "2"
        assert binds["filtro_2"] == "499"
        # não deve ter montado a cláusula de lista da coluna "nota" também
        # (a cláusula de filial também usa "IN", então checa especificamente
        # o padrão que a lista de "nota" geraria).
        assert f"{_comum.texto_coluna(self._COLUNA_SQL)} IN" not in sql

    def test_lista_e_faixa_juntas_geram_as_duas_clausulas(self):
        sql, binds = _montar_sql(
            self._COLUNAS_POR_VIEW,
            self._FILIAIS,
            {"vwia_notas_compra.nota": {"valores": ["000000002"], "min": "2", "max": "499"}},
            0,
        )
        # Faixa é processada antes da lista em `_montar_sql`, então os binds
        # da faixa saem primeiro (filtro_1/filtro_2) e o da lista depois.
        coluna_numerica = _comum.numero_coluna(self._COLUNA_SQL)
        assert f"{coluna_numerica} >= {_comum.numero_bind('filtro_1')}" in sql
        assert f"{coluna_numerica} <= {_comum.numero_bind('filtro_2')}" in sql
        assert f"{_comum.texto_coluna(self._COLUNA_SQL)} IN (:filtro_3)" in sql
        assert binds["filtro_3"] == "000000002"
