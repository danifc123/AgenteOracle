"""Cobre a lógica pura extraída de `relatorio_customizado.py` (ver
`relatorio_customizado_sql.py`) — resolução de JOIN por BFS e validação de
coluna, sem precisar de HTTP nem de banco (`_montar_sql`/`buscar_*` que
tocam banco não entram aqui, cobertos via integração em
`tests/integration/test_relatorio_customizado.py`)."""

import pytest

from agente_oracle.server.financeiro.relatorios.relatorio_customizado_sql import (
    RelatorioCustomizadoInvalido,
    _resolver_caminho_join,
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
