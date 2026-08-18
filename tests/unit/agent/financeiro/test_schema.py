import pytest

from agente_oracle.agent.financeiro.schema import VIEWS_DISPONIVEIS, inferir_tipo_filtro

# Conjunto de colunas REAIS de cada view, extraído direto do SELECT de
# db/views/financeiro_science.sql (fonte da verdade do banco) — não do que
# schema.py declara. Existe pra pegar exatamente o tipo de dessincronia que
# já aconteceu uma vez: schema.py descrevendo coluna/join que não existe na
# view real (ex: fornecedor_loja/cliente_loja/loja/filial em cadastro,
# tes_codigo, veiculo — nenhum desses existe no STAGE). Atualizar aqui junto
# se um dia uma coluna nova for adicionada de verdade à view no banco.
_COLUNAS_REAIS_POR_VIEW = {
    "vw_titulos_pagar": {
        "filial",
        "prefixo",
        "numero",
        "parcela",
        "tipo",
        "fornecedor_codigo",
        "fornecedor_nome",
        "natureza_codigo",
        "natureza_descricao",
        "data_emissao",
        "data_vencimento",
        "valor_original",
        "saldo_aberto",
        "valor_desconto",
        "valor_multa",
        "valor_juros",
        "data_baixa",
    },
    "vw_titulos_receber": {
        "filial",
        "prefixo",
        "numero",
        "parcela",
        "tipo",
        "cliente_codigo",
        "cliente_nome",
        "natureza_codigo",
        "natureza_descricao",
        "data_emissao",
        "data_vencimento",
        "valor_original",
        "saldo_aberto",
        "valor_desconto",
        "valor_multa",
        "valor_juros",
        "data_baixa",
    },
    "vw_fornecedores": {"codigo", "nome", "nome_reduzido", "cnpj_cpf", "tipo_pessoa", "estado"},
    "vw_clientes": {"codigo", "nome", "nome_reduzido", "cnpj_cpf", "tipo_pessoa", "estado", "municipio_nome"},
    "vw_pedidos_venda": {
        "filial",
        "numero_pedido",
        "item",
        "cliente_codigo",
        "cliente_nome",
        "data_emissao",
        "tipo_pedido",
        "codigo_safra",
        "natureza_codigo",
        "moeda",
        "produto_codigo",
        "produto_descricao",
        "grupo_produto_codigo",
        "quantidade_pedida",
        "quantidade_atendida",
        "saldo_pendente",
        "preco_unitario",
        "valor_total",
        "status_pedido",
    },
    "vw_faturamento": {
        "filial",
        "nota_fiscal",
        "serie",
        "item_nota",
        "pedido",
        "item_pedido",
        "cliente_codigo",
        "cliente_nome",
        "cliente_cnpj_cpf",
        "cliente_municipio",
        "cliente_uf",
        "data_emissao",
        "tipo_nota",
        "chave_nfe",
        "vendedor_codigo",
        "vendedor_nome",
        "tipo_frete",
        "produto_codigo",
        "produto_descricao",
        "grupo_produto_codigo",
        "codigo_safra",
        "natureza_codigo",
        "natureza_descricao",
        "quantidade",
        "valor_unitario",
        "valor_total",
        "custo",
    },
    "vw_movimento_bancario": {
        "filial",
        "banco_codigo",
        "banco_nome",
        "agencia",
        "conta",
        "data_disponivel",
        "historico",
        "recebimento_pagamento",
        "valor",
        "tipo_documento",
        "conciliado",
    },
    "vw_lancamentos_contabeis": {
        "filial",
        "documento",
        "linha",
        "conta",
        "conta_descricao",
        "centro_custo_debito",
        "centro_custo_credito",
        "historico",
        "valor",
        "data_movimentacao",
    },
}


def test_colunas_batem_com_a_view_real():
    for view in VIEWS_DISPONIVEIS:
        nomes = {coluna.nome for coluna in view.colunas}
        assert nomes == _COLUNAS_REAIS_POR_VIEW[view.nome], view.nome


def test_relacionamentos_so_usam_colunas_reais():
    for view in VIEWS_DISPONIVEIS:
        for relacionamento in view.relacionamentos:
            for coluna_local in relacionamento.colunas_locais:
                assert coluna_local in _COLUNAS_REAIS_POR_VIEW[view.nome], f"{view.nome}.{coluna_local}"
            for coluna_destino in relacionamento.colunas_destino:
                assert coluna_destino in _COLUNAS_REAIS_POR_VIEW[relacionamento.view_destino], (
                    f"{relacionamento.view_destino}.{coluna_destino}"
                )


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
