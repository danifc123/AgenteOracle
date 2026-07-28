import pytest

from agente_oracle.agent.financeiro.schema import inferir_tipo_filtro


def test_prefixo_data_vira_periodo_data():
    assert inferir_tipo_filtro("data_emissao") == "periodo-data"
    assert inferir_tipo_filtro("data_vencimento") == "periodo-data"


@pytest.mark.parametrize(
    "nome_coluna",
    ["valor_original", "quantidade_pedida", "saldo_aberto", "preco_unitario", "preço_venda", "custo"],
)
def test_palavras_numericas_viram_numero(nome_coluna):
    assert inferir_tipo_filtro(nome_coluna) == "numero"


def test_resto_vira_texto():
    assert inferir_tipo_filtro("cliente_nome") == "texto"
    assert inferir_tipo_filtro("fornecedor_codigo") == "texto"


def test_prefixo_data_tem_prioridade_sobre_palavra_numerica():
    # Coluna hipotética que começa com "data_" mas também contém "valor" —
    # a checagem de prefixo vem primeiro na função, então "periodo-data" ganha.
    assert inferir_tipo_filtro("data_valor_limite") == "periodo-data"
