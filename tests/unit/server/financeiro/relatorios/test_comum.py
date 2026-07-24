from decimal import Decimal

from agente_oracle.server.financeiro.relatorios import _comum


class _RequestFake:
    """`filiais_da_query`/`parametros_opcionais` só usam `request.query_params.get(...)` —
    um dict simples já satisfaz essa interface, sem precisar montar um Request de verdade."""

    def __init__(self, query_params: dict[str, str]):
        self.query_params = query_params


class TestSerializar:
    def test_decimal_vira_float(self):
        assert _comum.serializar(Decimal("10.5")) == 10.5

    def test_outros_tipos_passam_direto(self):
        assert _comum.serializar("texto") == "texto"
        assert _comum.serializar(None) is None
        assert _comum.serializar(42) == 42


class TestFiliaisDaQuery:
    def test_uma_filial(self):
        request = _RequestFake({"filial": "01"})
        assert _comum.filiais_da_query(request) == ["01"]

    def test_multiplas_filiais_separadas_por_virgula(self):
        request = _RequestFake({"filial": "01, 02 ,03"})
        assert _comum.filiais_da_query(request) == ["01", "02", "03"]

    def test_sem_filial_devolve_none(self):
        assert _comum.filiais_da_query(_RequestFake({})) is None

    def test_filial_so_com_espacos_devolve_none(self):
        assert _comum.filiais_da_query(_RequestFake({"filial": "   "})) is None


class TestParametrosOpcionais:
    def test_le_cada_campo_com_strip(self):
        request = _RequestFake({"cliente": " 123 ", "loja": "01"})
        resultado = _comum.parametros_opcionais(request, ("cliente", "loja", "vendedor"))
        assert resultado == {"cliente": "123", "loja": "01", "vendedor": ""}
