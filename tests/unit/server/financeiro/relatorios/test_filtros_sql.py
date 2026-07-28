from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in


def test_um_valor():
    clausula, binds = clausula_in("filial", ["01"])
    assert clausula == "(:filial_0)"
    assert binds == {"filial_0": "01"}


def test_tres_valores_mantem_a_ordem():
    clausula, binds = clausula_in("filial", ["01", "02", "03"])
    assert clausula == "(:filial_0, :filial_1, :filial_2)"
    assert binds == {"filial_0": "01", "filial_1": "02", "filial_2": "03"}


def test_lista_vazia():
    clausula, binds = clausula_in("filial", [])
    assert clausula == "()"
    assert binds == {}


def test_nome_base_diferente_muda_o_prefixo_dos_binds():
    clausula, binds = clausula_in("cliente", ["C0001"])
    assert clausula == "(:cliente_0)"
    assert binds == {"cliente_0": "C0001"}
