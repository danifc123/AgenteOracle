"""Cobre a lógica pura extraída de `relatorio_customizado.py` (ver
`relatorio_customizado_sql.py`) — resolução de JOIN por BFS e validação de
coluna, sem precisar de HTTP nem de banco (`_montar_sql`/`buscar_*` que
tocam banco não entram aqui, cobertos via integração em
`tests/integration/test_relatorio_customizado.py`)."""

import psycopg
import pytest

from agente_oracle.server.financeiro.relatorios import _comum, relatorio_customizado_sql
from agente_oracle.server.financeiro.relatorios.relatorio_customizado_sql import (
    RelatorioCustomizadoInvalido,
    ViewIndisponivel,
    _identificador_coluna,
    _levantar_se_view_inexistente,
    _montar_sql,
    _resolver_caminho_join,
    suporta_lista_opcoes,
    validar_coluna,
)


class TestValidarColuna:
    def test_coluna_existente(self):
        assert validar_coluna("vwia_clientes.codigo") == ("vwia_clientes", "codigo")

    def test_sem_ponto_e_invalido(self):
        assert validar_coluna("codigo") is None

    def test_view_inexistente(self):
        assert validar_coluna("vw_nao_existe.codigo") is None

    def test_coluna_inexistente_na_view(self):
        assert validar_coluna("vwia_clientes.coluna_que_nao_existe") is None


class TestResolverCaminhoJoin:
    def test_view_unica_nao_precisa_de_join(self):
        assert _resolver_caminho_join(["vwia_clientes"]) == []

    def test_relacionamento_direto(self):
        arestas = _resolver_caminho_join(["vwia_titulos_receber", "vwia_clientes"])
        assert arestas == [("vwia_titulos_receber", "vwia_clientes", ("cliente_codigo",), ("codigo",))]

    def test_relacionamento_no_sentido_inverso_da_declaracao(self):
        # `vwia_clientes` não declara relacionamento nenhum (é sempre o lado
        # "destino") — o grafo precisa funcionar nos dois sentidos.
        arestas = _resolver_caminho_join(["vwia_clientes", "vwia_titulos_receber"])
        assert arestas == [("vwia_clientes", "vwia_titulos_receber", ("codigo",), ("cliente_codigo",))]

    def test_caminho_indireto_por_view_intermediaria(self):
        # vwia_titulos_pagar -> vwia_fornecedores não tem caminho declarado até
        # vwia_clientes, mas vwia_faturamento conecta clientes e pedidos.
        arestas = _resolver_caminho_join(["vwia_faturamento", "vwia_pedidos_venda", "vwia_clientes"])
        views_nas_arestas = {view for _, view, _, _ in arestas}
        assert views_nas_arestas == {"vwia_pedidos_venda", "vwia_clientes"}

    def test_sem_relacionamento_declarado_levanta_erro(self):
        with pytest.raises(RelatorioCustomizadoInvalido):
            _resolver_caminho_join(["vwia_titulos_pagar", "vwia_clientes"])


class TestSuportaListaOpcoes:
    def test_coluna_texto_suporta(self):
        assert suporta_lista_opcoes("vwia_clientes", "nome") is True

    def test_coluna_texto_numerico_suporta(self):
        # "nota" tem `tipo_filtro="texto-numerico"` declarado (ver schema.py)
        # justamente pra também oferecer o modo lista, além da faixa.
        assert suporta_lista_opcoes("vwia_notas_compra", "nota") is True

    def test_coluna_numero_nao_suporta(self):
        assert suporta_lista_opcoes("vwia_titulos_pagar", "valor_original") is False

    def test_coluna_periodo_data_nao_suporta(self):
        assert suporta_lista_opcoes("vwia_titulos_pagar", "data_vencimento") is False


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


class TestMontarSqlFiltroPeriodoData:
    """Colunas "data_*" comuns (STAGE, DATE de verdade) comparam a coluna
    direto; colunas com `formato_data_texto` declarado (ex:
    vwia_baixas_pagar.data_baixa — texto "DD/MM/YYYY" na view real, não
    DATE) precisam do `TO_DATE(coluna, formato)` também do lado da coluna,
    senão comparar texto com DATE depende da conversão implícita do
    Oracle (formato da sessão, não necessariamente "DD/MM/YYYY")."""

    def test_coluna_date_real_nao_decora_a_coluna_com_to_date(self):
        sql, binds = _montar_sql(
            {"vwia_titulos_pagar": ["data_vencimento"]},
            ["0101"],
            {"vwia_titulos_pagar.data_vencimento": {"ini": "2026-01-01", "fim": "2026-01-31"}},
            0,
        )
        assert 'v0."DATA_VENCIMENTO" >= TO_DATE(:filtro_1' in sql
        assert 'v0."DATA_VENCIMENTO" <= TO_DATE(:filtro_2' in sql
        assert "TO_DATE(v0." not in sql
        assert binds["filtro_1"] == "2026-01-01"
        assert binds["filtro_2"] == "2026-01-31"

    def test_coluna_data_texto_decora_a_coluna_com_to_date_da_mascara_declarada(self):
        sql, _binds = _montar_sql(
            {"vwia_baixas_pagar": ["data_baixa"]},
            ["0101"],
            {"vwia_baixas_pagar.data_baixa": {"ini": "2026-01-01", "fim": "2026-01-31"}},
            0,
        )
        assert "TO_DATE(v0.\"data_baixa\", 'DD/MM/YYYY') >= TO_DATE(:filtro_1" in sql
        assert "TO_DATE(v0.\"data_baixa\", 'DD/MM/YYYY') <= TO_DATE(:filtro_2" in sql


class TestIdentificadorColuna:
    """As views do STAGE declaram alias sem aspas — no Oracle o nome
    real fica MAIÚSCULO; as do Protheus (`vwia_*`) declaram entre aspas em
    minúsculo. Citar do jeito errado dá ORA-00904."""

    def test_protheus_cita_em_minusculo(self):
        assert _identificador_coluna("protheus", "data_baixa") == '"data_baixa"'

    def test_stage_cita_em_maiusculo(self):
        assert _identificador_coluna("stage", "data_baixa") == '"DATA_BAIXA"'


class TestMontarSqlCitacaoPorFonte:
    def test_view_do_stage_usa_colunas_em_maiusculo_no_select_join_e_filial(self):
        sql, _binds = _montar_sql(
            {"vwia_titulos_receber": ["numero"], "vwia_clientes": ["nome"]}, ["0101"], {}, 0
        )
        assert 'v0."NUMERO" AS "vwia_titulos_receber.numero"' in sql
        assert 'v1."NOME" AS "vwia_clientes.nome"' in sql
        assert 'v0."CLIENTE_CODIGO" = v1."CODIGO"' in sql
        assert 'v0."FILIAL" IN' in sql
        assert '"filial"' not in sql

    def test_view_do_protheus_continua_em_minusculo(self):
        sql, _binds = _montar_sql({"vwia_notas_compra": ["nota"]}, ["0101"], {}, 0)
        assert 'v0."nota" AS "vwia_notas_compra.nota"' in sql
        assert 'v0."filial" IN' in sql


class TestLevantarSeViewInexistente:
    def test_ora_00942_vira_view_indisponivel_com_os_nomes_das_views(self):
        with pytest.raises(ViewIndisponivel, match="vwia_clientes, vwia_titulos_receber"):
            _levantar_se_view_inexistente(
                Exception("ORA-00942: table or view does not exist"),
                ["vwia_clientes", "vwia_titulos_receber"],
                "stage",
            )

    def test_view_indisponivel_continua_sendo_relatorio_customizado_invalido(self):
        assert issubclass(ViewIndisponivel, RelatorioCustomizadoInvalido)

    def test_outro_erro_de_banco_passa_sem_virar_view_indisponivel(self):
        _levantar_se_view_inexistente(Exception("ORA-00904: invalid identifier"), ["vwia_clientes"], "stage")

    def test_postgres_tabela_inexistente_tambem_e_reconhecida(self):
        class _ErroPg(psycopg.errors.UndefinedTable):
            pass

        with pytest.raises(ViewIndisponivel):
            _levantar_se_view_inexistente(_ErroPg("relation does not exist"), ["vwia_clientes"], "stage")


class TestBuscarOpcoesColunaViewInexistente:
    def test_view_ausente_no_banco_levanta_view_indisponivel_nao_erro_cru(self, monkeypatch):
        class _CursorSemView:
            def execute(self, _sql, **_binds):
                raise psycopg.errors.UndefinedTable("relation does not exist")

        class _Conexao:
            def cursor(self):
                return _CursorSemView()

        class _Contexto:
            def __enter__(self):
                return _Conexao()

            def __exit__(self, *_args):
                return False

        monkeypatch.setattr(
            relatorio_customizado_sql, "get_connection_para_fonte", lambda _fonte: _Contexto()
        )

        with pytest.raises(ViewIndisponivel, match="vwia_clientes"):
            relatorio_customizado_sql.buscar_opcoes_coluna("vwia_clientes", "nome")
