from decimal import Decimal

import pytest

from agente_oracle.agent.financeiro.schema import VIEWS_DISPONIVEIS, ColunaView, inferir_tipo_filtro


def _coluna(nome: str, tipo_filtro: str | None = None) -> ColunaView:
    """Monta uma `ColunaView` mínima só pra exercitar `inferir_tipo_filtro`
    — descrição não importa pra esses testes."""
    return ColunaView(nome, "descrição de teste", tipo_filtro=tipo_filtro)


# Conjunto de colunas REAIS de cada view, extraído direto do SELECT de
# db/views/financeiro_science.sql (fonte da verdade do banco) — não do que
# schema.py declara. Existe pra pegar exatamente o tipo de dessincronia que
# já aconteceu uma vez: schema.py descrevendo coluna/join que não existe na
# view real (ex: fornecedor_loja/cliente_loja/loja/filial em cadastro,
# tes_codigo, veiculo — nenhum desses existe no STAGE). Atualizar aqui junto
# se um dia uma coluna nova for adicionada de verdade à view no banco.
_COLUNAS_REAIS_POR_VIEW = {
    "vwia_titulos_pagar": {
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
    "vwia_titulos_receber": {
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
    "vwia_fornecedores": {"codigo", "nome", "nome_reduzido", "cnpj_cpf", "tipo_pessoa", "estado"},
    "vwia_clientes": {
        "codigo",
        "nome",
        "nome_reduzido",
        "cnpj_cpf",
        "tipo_pessoa",
        "estado",
        "municipio_nome",
    },
    "vwia_pedidos_venda": {
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
    "vwia_faturamento": {
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
    "vwia_movimento_bancario": {
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
    "vwia_lancamentos_contabeis": {
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
    "vwia_safra_cliente": {
        "cliente_codigo",
        "cultura",
        "safra_codigo",
        "safra_descricao",
        "safra_inicio",
        "safra_fim",
        "data_compra",
    },
    # Estas 3 views moram no Protheus HML (fonte="protheus"), não no STAGE —
    # conferido direto no catálogo Oracle (all_tab_columns), não em
    # financeiro_science.sql (que só descreve as views do STAGE). Nasceram
    # de uma view única (vw_titulos_pagar_completo) quebrada em 3 pra
    # separar o que é barato (cabeçalho de nota/título) do que é caro
    # (SE5_ENUMERADO/ROW_NUMBER da baixa) — só entra no SQL final quando o
    # usuário realmente marca uma coluna de vwia_baixas_pagar.
    "vwia_notas_compra": {
        "filial",
        "data_emissao",
        "nota",
        "serie",
        "natureza_codigo",
        "natureza_descricao",
        "fornecedor_codigo",
        "fornecedor_nome",
        "gera_duplicata",
        "atualiza_estoque",
        "prefixo",
        "tipo",
        "doc_financeiro",
        "numero_titulo",
        "parcela_titulo",
        "data_emissao_original",
        "data_vencimento_original",
        "valor_original_titulo",
        "valor_bruto_nf",
        "moeda_titulo",
        "taxa_moeda_origem",
        "taxa_data_emissao_nf",
        "valor_moeda_titulo",
        "valor_reais_titulo",
        "saldo_moeda_titulo",
        "saldo_aberto",
    },
    "vwia_devolucoes_compra": {
        "filial",
        "data_emissao_origem_compra",
        "numero_nota_origem",
        "serie_origem",
        "data_emissao",
        "nota",
        "serie",
        "natureza_codigo",
        "natureza_descricao",
        "fornecedor_codigo",
        "fornecedor_nome",
        "prefixo",
        "tipo",
        "doc_financeiro",
        "numero_titulo",
        "parcela_titulo",
        "data_emissao_original",
        "data_vencimento_original",
        "valor_original_titulo",
        "valor_bruto_nf",
        "moeda_titulo",
        "taxa_moeda_origem",
        "taxa_data_emissao_nf",
        "valor_moeda_titulo",
        "valor_reais_titulo",
        "saldo_moeda_titulo",
        "saldo_aberto",
    },
    "vwia_baixas_pagar": {
        "filial",
        "prefixo",
        "numero_titulo",
        "parcela_titulo",
        "tipo",
        "fornecedor_codigo",
        "seq_baixa",
        "tipo_doc_baixa",
        "desc_tipo_doc_baixa",
        "data_baixa",
        "taxa_data_baixa",
        "valor_baixado_moeda",
        "valor_baixado_reais",
        "valor_juros_baixa",
        "valor_multa_baixa",
        "valor_correcao_baixa",
        "valor_desconto_baixa",
        "valor_liquido_baixa",
        "motivo_baixa",
        "banco_baixa",
        "agencia_baixa",
        "conta_baixa",
        "documento_baixa",
        "recibo_baixa",
        "historico_baixa",
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
    assert inferir_tipo_filtro(_coluna("data_emissao")) == "periodo-data"
    assert inferir_tipo_filtro(_coluna("data_vencimento")) == "periodo-data"


@pytest.mark.parametrize(
    "nome_coluna",
    ["valor_original", "quantidade_pedida", "saldo_aberto", "preco_unitario", "preço_venda", "custo"],
)
def test_palavras_numericas_viram_numero(nome_coluna):
    assert inferir_tipo_filtro(_coluna(nome_coluna)) == "numero"


def test_resto_vira_texto():
    assert inferir_tipo_filtro(_coluna("cliente_nome")) == "texto"
    assert inferir_tipo_filtro(_coluna("fornecedor_codigo")) == "texto"


def test_prefixo_data_tem_prioridade_sobre_palavra_numerica():
    # Coluna hipotética que começa com "data_" mas também contém "valor" —
    # a checagem de prefixo vem primeiro na função, então "periodo-data" ganha.
    assert inferir_tipo_filtro(_coluna("data_valor_limite")) == "periodo-data"


def test_tipo_filtro_declarado_sobrescreve_heuristica():
    # "nota" não bate em nenhuma palavra numérica nem prefixo "data_" — sem
    # override cairia em "texto"; com `tipo_filtro` declarado, usa esse valor.
    assert inferir_tipo_filtro(_coluna("nota", tipo_filtro="texto-numerico")) == "texto-numerico"


def test_colunas_nota_das_views_vwia_declaram_texto_numerico():
    # As duas colunas "nota" reais (vwia_notas_compra, vwia_devolucoes_compra)
    # precisam do override pra oferecer filtro de faixa na tela, não só lista.
    colunas_nota = [coluna for view in VIEWS_DISPONIVEIS for coluna in view.colunas if coluna.nome == "nota"]
    assert colunas_nota, "esperava encontrar pelo menos uma coluna 'nota' nas views VWIA_*"
    for coluna in colunas_nota:
        assert inferir_tipo_filtro(coluna) == "texto-numerico"


# Colunas "data_*" das views VWIA_* que são texto formatado "DD/MM/YYYY" na
# view real (TO_CHAR(..., 'DD/MM/YYYY') em db/views/financeiro_science.sql),
# não DATE de verdade — precisam de `formato_data_texto` declarado, senão o
# filtro de período monta `TO_DATE(:bind, ...)` comparado direto contra
# texto, que falha ou dá resultado errado contra o Oracle real.
_COLUNAS_DATA_TEXTO_ESPERADAS = {
    ("vwia_notas_compra", "data_emissao"),
    ("vwia_notas_compra", "data_emissao_original"),
    ("vwia_notas_compra", "data_vencimento_original"),
    ("vwia_devolucoes_compra", "data_emissao_origem_compra"),
    ("vwia_devolucoes_compra", "data_emissao"),
    ("vwia_devolucoes_compra", "data_emissao_original"),
    ("vwia_devolucoes_compra", "data_vencimento_original"),
    ("vwia_baixas_pagar", "data_baixa"),
}


def test_colunas_data_texto_das_views_vwia_declaram_formato():
    encontradas = {
        (view.nome, coluna.nome)
        for view in VIEWS_DISPONIVEIS
        for coluna in view.colunas
        if coluna.formato_data_texto is not None
    }
    assert encontradas == _COLUNAS_DATA_TEXTO_ESPERADAS


def test_colunas_data_texto_continuam_tipo_periodo_data():
    # `formato_data_texto` muda só como o SQL do filtro é montado
    # (relatorio_customizado_sql.py) — o tipo de filtro/widget na tela
    # continua "periodo-data", igual qualquer outra coluna "data_*".
    for view in VIEWS_DISPONIVEIS:
        for coluna in view.colunas:
            if coluna.formato_data_texto is not None:
                assert inferir_tipo_filtro(coluna) == "periodo-data", f"{view.nome}.{coluna.nome}"


def test_colunas_data_sem_override_nao_declaram_formato_texto():
    # As demais colunas "data_*" (STAGE, DATE de verdade) não devem ganhar
    # `formato_data_texto` por engano.
    for view in VIEWS_DISPONIVEIS:
        for coluna in view.colunas:
            if (
                coluna.nome.startswith("data_")
                and (view.nome, coluna.nome) not in _COLUNAS_DATA_TEXTO_ESPERADAS
            ):
                assert coluna.formato_data_texto is None, f"{view.nome}.{coluna.nome}"


def _coluna_da_view(nome_view: str, nome_coluna: str) -> ColunaView:
    view = next(item for item in VIEWS_DISPONIVEIS if item.nome == nome_view)
    return next(coluna for coluna in view.colunas if coluna.nome == nome_coluna)


class TestRotuloDe:
    _COLUNA = ColunaView("conciliado", "teste", rotulos=(("1", "Sim"), ("0", "Não")))

    def test_valor_com_rotulo_devolve_o_rotulo(self):
        assert self._COLUNA.rotulo_de("1") == "Sim"

    @pytest.mark.parametrize("valor", [1, 1.0, Decimal("1"), Decimal("1.0"), " 1 "])
    def test_numero_inteiro_em_qualquer_forma_bate_com_a_mesma_chave(self, valor):
        # O Oracle devolve NUMBER como int, Decimal ou float conforme o driver.
        assert self._COLUNA.rotulo_de(valor) == "Sim"

    def test_valor_sem_rotulo_aparece_como_veio(self):
        assert self._COLUNA.rotulo_de("EMP") == "EMP"

    def test_numero_nao_inteiro_sem_rotulo_nao_quebra(self):
        assert self._COLUNA.rotulo_de(1.5) == "1.5"

    @pytest.mark.parametrize("valor", [float("nan"), float("inf"), Decimal("NaN")])
    def test_numero_nao_finito_nao_levanta_erro(self, valor):
        assert self._COLUNA.rotulo_de(valor) == str(valor)

    def test_coluna_sem_rotulos_devolve_o_valor_como_texto(self):
        assert ColunaView("qualquer", "teste").rotulo_de("X") == "X"


class TestRotulosDasViewsDoStage:
    def test_nenhuma_coluna_repete_chave_de_rotulo(self):
        for view in VIEWS_DISPONIVEIS:
            for coluna in view.colunas:
                chaves = [chave for chave, _rotulo in coluna.rotulos]
                assert len(chaves) == len(set(chaves)), f"{view.nome}.{coluna.nome}"

    def test_so_views_do_stage_declaram_rotulos(self):
        # Escopo combinado: Protheus fica de fora por enquanto.
        for view in VIEWS_DISPONIVEIS:
            if view.fonte != "stage":
                assert all(not coluna.rotulos for coluna in view.colunas), view.nome

    @pytest.mark.parametrize(
        ("nome_view", "nome_coluna", "valor_cru", "rotulo_esperado"),
        [
            ("vwia_movimento_bancario", "recebimento_pagamento", "R", "Recebimento"),
            ("vwia_movimento_bancario", "recebimento_pagamento", "P", "Pagamento"),
            ("vwia_movimento_bancario", "conciliado", 1, "Sim"),
            ("vwia_movimento_bancario", "conciliado", 0, "Não"),
            ("vwia_faturamento", "tipo_frete", "C", "CIF"),
            ("vwia_faturamento", "tipo_frete", "-1", "Não informado"),
            ("vwia_faturamento", "codigo_safra", "-1", "Sem safra"),
            ("vwia_clientes", "tipo_pessoa", "F", "Pessoa física"),
            ("vwia_fornecedores", "tipo_pessoa", "INDEFINIDO", "Não informado"),
            ("vwia_pedidos_venda", "moeda", "2", "Dólar"),
            ("vwia_titulos_pagar", "tipo", "NF", "Nota fiscal"),
            ("vwia_titulos_receber", "tipo", "IR-", "IRRF (abatimento)"),
            ("vwia_lancamentos_contabeis", "conta", "-1", "Sem conta definida"),
        ],
    )
    def test_rotulo_cadastrado(self, nome_view, nome_coluna, valor_cru, rotulo_esperado):
        assert _coluna_da_view(nome_view, nome_coluna).rotulo_de(valor_cru) == rotulo_esperado

    @pytest.mark.parametrize("sigla", ["EMP", "FD", "FD-", "FU-", "FOL", "IMA", "SEN", "FUN", "INP"])
    def test_sigla_de_titulo_sem_significado_confirmado_continua_como_veio(self, sigla):
        # Não inventar: essas siglas parecem da empresa e ninguém confirmou o significado.
        assert _coluna_da_view("vwia_titulos_pagar", "tipo").rotulo_de(sigla) == sigla


class TestDatasDeSafra:
    @pytest.mark.parametrize("nome_coluna", ["safra_inicio", "safra_fim"])
    def test_datas_de_safra_viram_filtro_de_periodo(self, nome_coluna):
        # São DATE de verdade, mas o nome não começa com "data_" — sem o
        # override a heurística as tratava como lista de texto.
        assert inferir_tipo_filtro(_coluna_da_view("vwia_safra_cliente", nome_coluna)) == "periodo-data"
