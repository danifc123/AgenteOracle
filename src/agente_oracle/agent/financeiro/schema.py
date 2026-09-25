"""Schema financeiro que a IA tem permissão de consultar via
`executar_consulta_financeira` — fonte única de verdade compartilhada entre o
prompt do agente (`agent/financeiro/prompt.py`) e a validação de segurança da
tool de SQL livre (`tools/financeiro/consulta_livre.py`), pra nunca ficarem
dessincronizadas (o prompt prometendo uma view que a validação não libera, ou
vice-versa).

Fica vazio até as views financeiras serem criadas no banco (view + usuário
Oracle somente leitura restrito a elas, sem acesso às tabelas reais do
TOTVS) — enquanto isso, tanto o prompt quanto a validação tratam como
"nenhuma view liberada" e a IA não gera SQL nenhum.
"""

from dataclasses import dataclass
from decimal import Decimal

# Prefixo das tools MCP deste módulo (ex: "financeiro_executar_consulta_financeira").
# Usado tanto no registro das tools (server/financeiro/ia.py) quanto na hora de
# filtrar quais tools cada agente enxerga (agent/cli.py, server/financeiro/ia.py) —
# assim, quando outro módulo (Compras, RH...) registrar tools no mesmo servidor
# MCP, o agente do Financeiro continua só vendo e só podendo chamar as dele.
PREFIXO_TOOL: str = "financeiro_"

# Máscara usada por `ColunaView.formato_data_texto` nas colunas de data das
# views do Protheus (`fonte="protheus"`) que guardam o valor como texto (`TO_CHAR(..., 'DD/MM/YYYY')`
# em db/views/financeiro_science.sql), não como DATE de verdade — mesma
# máscara em todas elas, daí a constante em vez de repetir a string solta.
_FORMATO_DATA_BR = "DD/MM/YYYY"


@dataclass(frozen=True)
class ColunaView:
    """Uma coluna de uma view financeira, com descrição curta pra IA entender o que ela guarda.

    `tipo_filtro` é opcional e só existe pra sobrescrever a heurística de
    `inferir_tipo_filtro()` (baseada no nome) quando ela erra pra uma coluna
    específica — ex: "nota" é um código de texto zero-padded ("000000002"),
    mas o usuário quer poder filtrar por faixa numérica também, então essa
    coluna declara `tipo_filtro="texto-numerico"` em vez de cair no "texto"
    genérico (lista de valores exatos) que o nome sozinho sugeriria.

    `formato_data_texto` é opcional e só existe pras colunas "data_*" que,
    apesar do nome, NÃO são DATE de verdade na view — várias colunas das
    views do Protheus (`db/views/financeiro_science.sql`) guardam a data já
    formatada como texto (`TO_CHAR(..., 'DD/MM/YYYY')`), herdado do
    Protheus cru. `_montar_sql` (`relatorio_customizado_sql.py`) usa esse
    valor como máscara pra fazer `TO_DATE(coluna, formato_data_texto)`
    antes de comparar no filtro de período — sem isso, comparar o texto
    direto com uma DATE depende da conversão implícita do Oracle (formato
    da sessão, não necessariamente "DD/MM/YYYY"), o que falha ou dá
    resultado errado. `None` (padrão) = coluna é DATE de verdade, sem
    cast nenhum, comportamento inalterado pra todas as outras views.

    `rotulos` (valor cru → texto legível) vale só na apresentação do "Criar Relatório":
    o banco, os filtros e quem consome a view seguem com o valor cru."""

    nome: str
    descricao: str
    tipo_filtro: str | None = None
    formato_data_texto: str | None = None
    rotulos: tuple[tuple[str, str], ...] = ()

    def rotulo_de(self, valor) -> str:
        """Rótulo do valor cru, ou o próprio valor quando não há rótulo."""
        return dict(self.rotulos).get(_chave_rotulo(valor), str(valor))


def _chave_rotulo(valor) -> str:
    """Forma comparável do valor: inteiro vira texto (`1.0` → `'1'`), o resto sem espaços."""
    if isinstance(valor, int | float | Decimal) and not isinstance(valor, bool):
        try:
            if valor == int(valor):
                return str(int(valor))
        except (ArithmeticError, ValueError):
            pass
    return str(valor).strip()


@dataclass(frozen=True)
class RelacionamentoView:
    """Uma relação de chave estrangeira entre views: as colunas desta view
    (`colunas_locais`) correspondem às colunas (`colunas_destino`, na mesma
    ordem) da view referenciada (`view_destino`) — usado pra montar JOIN.
    Declarar aqui, junto das colunas, é o que faz o texto de relacionamentos
    do prompt (`agent/financeiro/prompt.py`) se gerar sozinho — sem isso, a
    IA não sabe como cruzar dado de uma view com outra e ou inventa nome de
    coluna, ou recusa um pedido que na verdade é só um JOIN."""

    view_destino: str
    colunas_locais: tuple[str, ...]
    colunas_destino: tuple[str, ...]
    descricao: str = ""


@dataclass(frozen=True)
class ViewFinanceira:
    """Uma view liberada para o agente consultar. `nome` precisa bater exatamente
    com o nome real da view no banco (Oracle deixa identificadores em maiúsculas
    por padrão, salvo uso de aspas).

    `fonte` diz qual conexão Oracle tem essa view — "stage" (padrão, `STAGE`/
    `SCIENCE_PROD`, roteado por `DB_BACKEND`) ou "protheus" (Protheus HML,
    `get_protheus_connection`). São duas instâncias Oracle diferentes, sem
    `DB LINK` entre elas — por isso nunca declare `RelacionamentoView` entre
    views de fontes diferentes: não existe SQL único capaz de fazer esse JOIN
    (ver `relatorio_customizado_sql.py::_fonte_comum`, que bloqueia a
    combinação antes de tentar montar a query).

    Por que existem as duas fontes (e não só uma): ver o docstring do módulo
    `db/connection.py` — resumo rápido, o STAGE é um espelho ETL achatado
    (um título = uma linha só, sem baixa a baixa) e só serve pra relatório
    "visão simples"; quando o relatório precisa do ciclo completo da nota
    (baixa a baixa, devolução), só o Protheus transacional tem esse nível
    de detalhe."""

    nome: str
    descricao: str
    colunas: tuple[ColunaView, ...]
    relacionamentos: tuple[RelacionamentoView, ...] = ()
    fonte: str = "stage"


# Rótulos do STAGE (`ColunaView.rotulos`). `-1` é o placeholder de nulo do Pentaho.
# Siglas sem significado confirmado ficam de fora: aparecem como vêm.
_ROTULOS_SIM_NAO = (("1", "Sim"), ("0", "Não"))
_ROTULOS_RECEBIMENTO_PAGAMENTO = (("R", "Recebimento"), ("P", "Pagamento"))
_ROTULOS_TIPO_PESSOA = (("F", "Pessoa física"), ("J", "Pessoa jurídica"), ("INDEFINIDO", "Não informado"))
_ROTULOS_TIPO_FRETE = (
    ("C", "CIF"),
    ("F", "FOB"),
    ("T", "Por conta de terceiros"),
    ("R", "Por conta do remetente"),
    ("D", "Por conta do destinatário"),
    ("S", "Sem frete"),
    ("-1", "Não informado"),
)
# Mesma lista de moedas já decodificada em `vwia_notas_compra` (Protheus).
_ROTULOS_MOEDA = (
    ("1", "Real"),
    ("2", "Dólar"),
    ("3", "UFIR"),
    ("4", "Euro"),
    ("5", "Iene"),
    ("6", "Soja"),
    ("7", "Milho"),
    ("8", "Sorgo"),
)
# Mesma redação de `DESCRICAO_TIPO_DOC` em `vwia_baixas_pagar`; "DH" (Dinheiro)
# não está lá e ainda precisa de confirmação.
_ROTULOS_TIPO_DOCUMENTO_BANCARIO = (
    ("VL", "Baixa com movimento bancário"),
    ("TR", "Transferência"),
    ("DH", "Dinheiro"),
    ("PA", "Pagamento antecipado"),
    ("TE", "Transferência estornada"),
    ("RA", "Recebimento antecipado"),
    ("ES", "Estorno"),
    ("AP", "Aplicação financeira"),
    ("-1", "Não informado"),
)
_ROTULOS_SEM_SAFRA = (("-1", "Sem safra"),)
_ROTULOS_SEM_CONTA = (("-1", "Sem conta definida"),)
_ROTULOS_SEM_CENTRO_CUSTO = (("-1", "Sem centro de custo"),)
# Padrão TOTVS. Ficam de fora (sem confirmação): EMP, FD, FD-, FU-, FOL, IMA,
# SEN, FUN, INP, CSS, DDI, TXA, NP, NDI, DH.
_ROTULOS_TIPO_TITULO = (
    ("NF", "Nota fiscal"),
    ("TX", "Taxa"),
    ("PA", "Pagamento antecipado"),
    ("RA", "Recebimento antecipado"),
    ("NDF", "Nota de débito de fornecedor"),
    ("NCC", "Nota de crédito de cliente"),
    ("NCF", "Nota de crédito de fornecedor"),
    ("CH", "Cheque"),
    ("DP", "Duplicata"),
    ("FT", "Fatura"),
    ("BOL", "Boleto"),
    ("RC", "Recibo"),
    ("PR", "Provisório"),
    ("CR", "Cartão de crédito"),
    ("ISS", "ISS"),
    ("INS", "INSS"),
    ("IRF", "IRRF"),
    ("PIS", "PIS"),
    ("COF", "COFINS"),
    ("CSL", "CSLL"),
    ("IR-", "IRRF (abatimento)"),
    ("PI-", "PIS (abatimento)"),
    ("CS-", "CSLL (abatimento)"),
    ("CF-", "COFINS (abatimento)"),
    ("AB-", "Abatimento"),
)

VIEWS_DISPONIVEIS: tuple[ViewFinanceira, ...] = (
    ViewFinanceira(
        nome="vwia_titulos_pagar",
        descricao="Títulos a pagar (contas a pagar a fornecedores), um por parcela.",
        colunas=(
            ColunaView("filial", "código da filial"),
            ColunaView("prefixo", "prefixo do documento"),
            ColunaView("numero", "número do título"),
            ColunaView("parcela", "número da parcela"),
            ColunaView("tipo", "tipo do título (ex: NF)", rotulos=_ROTULOS_TIPO_TITULO),
            ColunaView("fornecedor_codigo", "código do fornecedor"),
            ColunaView("fornecedor_nome", "nome do fornecedor"),
            ColunaView("natureza_codigo", "código da natureza financeira"),
            ColunaView("natureza_descricao", "descrição da natureza financeira"),
            ColunaView("data_emissao", "data de emissão do título"),
            ColunaView("data_vencimento", "data de vencimento real do título"),
            ColunaView("valor_original", "valor original do título"),
            ColunaView(
                "saldo_aberto",
                "valor numérico do saldo em aberto — NÃO é um flag/booleano. "
                "0 = título já quitado; qualquer valor MAIOR QUE 0 = título em aberto "
                "(use 'saldo_aberto > 0', nunca 'saldo_aberto = 1')",
            ),
            ColunaView("valor_desconto", "valor de desconto obtido no pagamento (0 se não houve)"),
            ColunaView("valor_multa", "valor de multa paga por atraso (0 se não houve)"),
            ColunaView("valor_juros", "valor de juros pago por atraso (0 se não houve)"),
            ColunaView(
                "data_baixa",
                "data em que o título foi efetivamente pago — NULL enquanto o título "
                "estiver em aberto (saldo_aberto > 0)",
            ),
        ),
        relacionamentos=(
            RelacionamentoView(
                view_destino="vwia_fornecedores",
                colunas_locais=("fornecedor_codigo",),
                colunas_destino=("codigo",),
                descricao=(
                    "Dado de fornecedor que não está aqui (cnpj_cpf, tipo_pessoa, "
                    "nome_reduzido, estado) só existe em vwia_fornecedores."
                ),
            ),
        ),
    ),
    ViewFinanceira(
        nome="vwia_titulos_receber",
        descricao="Títulos a receber (contas a receber de clientes), um por parcela.",
        colunas=(
            ColunaView("filial", "código da filial"),
            ColunaView("prefixo", "prefixo do documento"),
            ColunaView("numero", "número do título"),
            ColunaView("parcela", "número da parcela"),
            ColunaView("tipo", "tipo do título (ex: NF, NP)", rotulos=_ROTULOS_TIPO_TITULO),
            ColunaView("cliente_codigo", "código do cliente"),
            ColunaView("cliente_nome", "nome do cliente"),
            ColunaView("natureza_codigo", "código da natureza financeira"),
            ColunaView("natureza_descricao", "descrição da natureza financeira"),
            ColunaView("data_emissao", "data de emissão do título"),
            ColunaView("data_vencimento", "data de vencimento real do título"),
            ColunaView("valor_original", "valor original do título"),
            ColunaView(
                "saldo_aberto",
                "valor numérico do saldo em aberto — NÃO é um flag/booleano. "
                "0 = título já quitado; qualquer valor MAIOR QUE 0 = título em aberto "
                "(use 'saldo_aberto > 0', nunca 'saldo_aberto = 1')",
            ),
            ColunaView("valor_desconto", "valor de desconto obtido no recebimento (0 se não houve)"),
            ColunaView("valor_multa", "valor de multa recebida por atraso (0 se não houve)"),
            ColunaView("valor_juros", "valor de juros recebido por atraso (0 se não houve)"),
            ColunaView(
                "data_baixa",
                "data em que o título foi efetivamente recebido — NULL enquanto o título "
                "estiver em aberto (saldo_aberto > 0)",
            ),
        ),
        relacionamentos=(
            RelacionamentoView(
                view_destino="vwia_clientes",
                colunas_locais=("cliente_codigo",),
                colunas_destino=("codigo",),
                descricao=(
                    "Dado de cliente que não está aqui (cnpj_cpf, tipo_pessoa, "
                    "nome_reduzido, estado) só existe em vwia_clientes."
                ),
            ),
        ),
    ),
    ViewFinanceira(
        nome="vwia_fornecedores",
        descricao="Cadastro de fornecedores.",
        colunas=(
            ColunaView(
                "codigo",
                "código do fornecedor — aqui o nome da coluna é `codigo`, NUNCA "
                "`fornecedor_codigo` (esse nome com prefixo só existe em vwia_titulos_pagar).",
            ),
            ColunaView("nome", "razão social / nome completo"),
            ColunaView("nome_reduzido", "nome reduzido/fantasia"),
            ColunaView("cnpj_cpf", "CNPJ ou CPF"),
            ColunaView("tipo_pessoa", "F = pessoa física, J = pessoa jurídica", rotulos=_ROTULOS_TIPO_PESSOA),
            ColunaView(
                "estado",
                "sigla de 2 letras do estado (UF), ex: 'MT', 'SP', 'MG' — nunca o nome "
                "completo. Se o usuário mencionar o nome completo do estado (ex: "
                "'Mato Grosso', 'São Paulo'), converta você mesmo para a sigla "
                "correspondente antes de montar o WHERE (ex: estado = 'MT').",
            ),
        ),
    ),
    ViewFinanceira(
        nome="vwia_clientes",
        descricao="Cadastro de clientes.",
        colunas=(
            ColunaView(
                "codigo",
                "código do cliente — aqui o nome da coluna é `codigo`, NUNCA "
                "`cliente_codigo` (esse nome com prefixo só existe em vwia_titulos_receber).",
            ),
            ColunaView("nome", "razão social / nome completo"),
            ColunaView("nome_reduzido", "nome reduzido/fantasia"),
            ColunaView("cnpj_cpf", "CNPJ ou CPF"),
            ColunaView("tipo_pessoa", "F = pessoa física, J = pessoa jurídica", rotulos=_ROTULOS_TIPO_PESSOA),
            ColunaView(
                "estado",
                "sigla de 2 letras do estado (UF), ex: 'MT', 'SP', 'MG' — nunca o nome "
                "completo. Se o usuário mencionar o nome completo do estado (ex: "
                "'Mato Grosso', 'São Paulo'), converta você mesmo para a sigla "
                "correspondente antes de montar o WHERE (ex: estado = 'MT').",
            ),
            ColunaView("municipio_nome", "nome do município (cidade) do cliente"),
        ),
    ),
    ViewFinanceira(
        nome="vwia_pedidos_venda",
        descricao=(
            "Posição de pedidos de venda, um registro por item de pedido — inclui pedidos "
            "ainda não faturados (saldo pendente > 0)."
        ),
        colunas=(
            ColunaView("filial", "código da filial"),
            ColunaView("numero_pedido", "número do pedido de venda"),
            ColunaView("item", "número do item dentro do pedido"),
            ColunaView("cliente_codigo", "código do cliente"),
            ColunaView("cliente_nome", "razão social / nome completo do cliente"),
            ColunaView("data_emissao", "data de emissão do pedido"),
            ColunaView("tipo_pedido", "tipo do pedido de venda"),
            ColunaView("codigo_safra", "código da safra vinculada ao pedido", rotulos=_ROTULOS_SEM_SAFRA),
            ColunaView("natureza_codigo", "código da natureza financeira do pedido"),
            ColunaView("moeda", "código da moeda do pedido", rotulos=_ROTULOS_MOEDA),
            ColunaView("produto_codigo", "código do produto"),
            ColunaView("produto_descricao", "descrição do produto"),
            ColunaView("grupo_produto_codigo", "código do grupo do produto"),
            ColunaView("quantidade_pedida", "quantidade total pedida no item"),
            ColunaView("quantidade_atendida", "quantidade já entregue/faturada do item"),
            ColunaView(
                "saldo_pendente",
                "quantidade ainda não entregue (quantidade_pedida - quantidade_atendida) — "
                "0 quando o item já foi totalmente atendido",
            ),
            ColunaView("preco_unitario", "preço unitário de venda do item"),
            ColunaView("valor_total", "valor total do item (quantidade x preço)"),
            ColunaView(
                "status_pedido",
                "status calculado do item: AGUARDANDO LIBERACAO, LIBERADO, BLOQUEADO POR REGRA, "
                "BLOQUEADO POR VERBA, CANCELADO, FATURADO PARCIAL ou FATURADO TOTAL",
            ),
            ColunaView("natureza_descricao", "descrição da natureza financeira do pedido"),
            ColunaView("grupo_produto_descricao", "descrição do grupo do produto"),
        ),
        relacionamentos=(
            RelacionamentoView(
                view_destino="vwia_clientes",
                colunas_locais=("cliente_codigo",),
                colunas_destino=("codigo",),
                descricao="Dado de cliente que não está aqui (cnpj_cpf, estado etc.) só existe em vwia_clientes.",
            ),
            RelacionamentoView(
                view_destino="vwia_faturamento",
                colunas_locais=("filial", "numero_pedido", "item"),
                colunas_destino=("filial", "pedido", "item_pedido"),
                descricao=(
                    "Notas fiscais que faturaram este item de pedido — um pedido pode ter várias "
                    "notas (faturamento parcial) ou nenhuma ainda (saldo_pendente > 0)."
                ),
            ),
        ),
    ),
    ViewFinanceira(
        nome="vwia_faturamento",
        descricao=(
            "Faturamento detalhado, um registro por item de nota fiscal de saída já emitida "
            "(pedidos ainda não faturados não aparecem aqui — veja vwia_pedidos_venda)."
        ),
        colunas=(
            ColunaView("filial", "código da filial"),
            ColunaView("nota_fiscal", "número da nota fiscal"),
            ColunaView("serie", "série da nota fiscal"),
            ColunaView("item_nota", "número do item dentro da nota fiscal"),
            ColunaView("pedido", "número do pedido de venda que originou esta nota"),
            ColunaView("item_pedido", "número do item do pedido que originou este item de nota"),
            ColunaView("cliente_codigo", "código do cliente (ou fornecedor, se a nota for de devolução)"),
            ColunaView("cliente_nome", "razão social / nome completo do cliente"),
            ColunaView("cliente_cnpj_cpf", "CNPJ ou CPF do cliente"),
            ColunaView("cliente_municipio", "município do cliente"),
            ColunaView("cliente_uf", "sigla do estado (UF) do cliente"),
            ColunaView("data_emissao", "data de emissão da nota fiscal"),
            ColunaView("tipo_nota", "tipo da nota fiscal (ex: normal, devolução)"),
            ColunaView("chave_nfe", "chave de acesso da NF-e"),
            ColunaView("vendedor_codigo", "código do vendedor"),
            ColunaView("vendedor_nome", "nome do vendedor"),
            ColunaView("tipo_frete", "código do tipo de frete (CIF/FOB/etc.)", rotulos=_ROTULOS_TIPO_FRETE),
            ColunaView("produto_codigo", "código do produto"),
            ColunaView("produto_descricao", "descrição do produto"),
            ColunaView("grupo_produto_codigo", "código do grupo do produto"),
            ColunaView(
                "codigo_safra",
                "código da safra vinculada ao pedido de origem",
                rotulos=_ROTULOS_SEM_SAFRA,
            ),
            ColunaView("natureza_codigo", "código da natureza financeira do pedido de origem"),
            ColunaView("natureza_descricao", "descrição da natureza financeira"),
            ColunaView("quantidade", "quantidade faturada no item"),
            ColunaView("valor_unitario", "valor unitário de venda do item"),
            ColunaView("valor_total", "valor total do item (quantidade x valor unitário)"),
            ColunaView("custo", "custo do item na data do faturamento"),
            ColunaView("grupo_produto_descricao", "descrição do grupo do produto"),
        ),
        relacionamentos=(
            RelacionamentoView(
                view_destino="vwia_clientes",
                colunas_locais=("cliente_codigo",),
                colunas_destino=("codigo",),
                descricao="Dado de cliente que não está aqui (cnpj_cpf duplicado, estado etc.) também existe em vwia_clientes.",
            ),
            RelacionamentoView(
                view_destino="vwia_pedidos_venda",
                colunas_locais=("filial", "pedido", "item_pedido"),
                colunas_destino=("filial", "numero_pedido", "item"),
                descricao="Pedido de venda que originou esta nota fiscal.",
            ),
            RelacionamentoView(
                view_destino="vwia_titulos_receber",
                colunas_locais=("filial", "nota_fiscal", "serie", "cliente_codigo"),
                colunas_destino=("filial", "numero", "prefixo", "cliente_codigo"),
                descricao=(
                    "Títulos a receber gerados por esta nota fiscal (considere apenas os títulos "
                    "com tipo = 'NF' em vwia_titulos_receber)."
                ),
            ),
        ),
    ),
    ViewFinanceira(
        nome="vwia_movimento_bancario",
        descricao="Movimentações bancárias (recebimentos, pagamentos e baixas) por conta.",
        colunas=(
            ColunaView("filial", "código da filial"),
            ColunaView("banco_codigo", "código do banco"),
            ColunaView("banco_nome", "nome reduzido do banco/conta"),
            ColunaView("agencia", "agência bancária"),
            ColunaView("conta", "número da conta"),
            ColunaView("data_disponivel", "data em que o valor ficou disponível na conta"),
            ColunaView("historico", "descrição/histórico do lançamento"),
            ColunaView(
                "recebimento_pagamento",
                "R = recebimento, P = pagamento",
                rotulos=_ROTULOS_RECEBIMENTO_PAGAMENTO,
            ),
            ColunaView("valor", "valor do lançamento"),
            ColunaView(
                "tipo_documento",
                "tipo do documento (ex: RB recebimento, PG pagamento)",
                rotulos=_ROTULOS_TIPO_DOCUMENTO_BANCARIO,
            ),
            ColunaView(
                "conciliado",
                "1 se o lançamento já foi conciliado com o extrato do banco, 0 se não — "
                "não é um tipo booleano de verdade (Oracle SQL não tem), é numérico",
                rotulos=_ROTULOS_SIM_NAO,
            ),
        ),
    ),
    ViewFinanceira(
        nome="vwia_lancamentos_contabeis",
        descricao="Lançamentos de contabilidade (partidas de débito/crédito), um registro por linha.",
        colunas=(
            ColunaView("filial", "código da filial"),
            ColunaView("documento", "número do documento do lançamento"),
            ColunaView("linha", "número da linha dentro do documento"),
            ColunaView(
                "conta",
                "código da conta contábil (plano de contas) — '-1' significa que o "
                "lançamento NÃO tem conta definida ainda",
                rotulos=_ROTULOS_SEM_CONTA,
            ),
            ColunaView("conta_descricao", "descrição da conta contábil, NULL quando conta = '-1'"),
            ColunaView(
                "centro_custo_debito",
                "centro de custo do lado devedor do lançamento — '-1' quando não definido",
                rotulos=_ROTULOS_SEM_CENTRO_CUSTO,
            ),
            ColunaView(
                "centro_custo_credito",
                "centro de custo do lado credor do lançamento — '-1' quando não definido",
                rotulos=_ROTULOS_SEM_CENTRO_CUSTO,
            ),
            ColunaView("historico", "descrição livre do lançamento"),
            ColunaView("valor", "valor do lançamento"),
            ColunaView("data_movimentacao", "data do lançamento contábil"),
        ),
    ),
    ViewFinanceira(
        nome="vwia_safra_cliente",
        descricao=(
            "Cultura e safra de cada compra de um cliente — um registro por compra, não "
            "deduplicado (cliente pode ter comprado semente de mais de uma cultura/safra)."
        ),
        colunas=(
            ColunaView("cliente_codigo", "código do cliente que fez a compra"),
            ColunaView("cultura", "cultura do produto comprado (ex: SOJA, MILHO, ALGODAO)"),
            ColunaView("safra_codigo", "código da safra (ex: '2025/2026')"),
            ColunaView("safra_descricao", "descrição da safra (ex: 'SAFRA 25/26')"),
            ColunaView("safra_inicio", "data de início da janela da safra", tipo_filtro="periodo-data"),
            ColunaView("safra_fim", "data de fim da janela da safra", tipo_filtro="periodo-data"),
            ColunaView("data_compra", "data de emissão da nota fiscal dessa compra"),
        ),
        relacionamentos=(
            RelacionamentoView(
                view_destino="vwia_clientes",
                colunas_locais=("cliente_codigo",),
                colunas_destino=("codigo",),
                descricao="Dado de cadastro do cliente (nome, município etc.) só existe em vwia_clientes.",
            ),
        ),
    ),
    ViewFinanceira(
        nome="vwia_notas_compra",
        descricao="Nota de entrada (compra) até o título a pagar — sem dado de baixa (ver vwia_baixas_pagar).",
        colunas=(
            ColunaView("filial", "código da filial"),
            ColunaView("data_emissao", "data de emissão desta nota", formato_data_texto=_FORMATO_DATA_BR),
            ColunaView(
                "nota",
                "número desta nota fiscal",
                tipo_filtro="texto-numerico",
            ),
            ColunaView("serie", "série desta nota fiscal"),
            ColunaView("natureza_codigo", "código da natureza financeira"),
            ColunaView("natureza_descricao", "descrição da natureza financeira"),
            ColunaView("fornecedor_codigo", "código do fornecedor + loja, formato 'codigo - loja'"),
            ColunaView("fornecedor_nome", "razão social do fornecedor"),
            ColunaView("gera_duplicata", "flag do tipo de entrada de estoque (TES): se gera título a pagar"),
            ColunaView("atualiza_estoque", "flag do tipo de entrada de estoque (TES): se movimenta estoque"),
            ColunaView("prefixo", "prefixo do título a pagar"),
            ColunaView("tipo", "tipo do título (sempre 'NF' nesta view — compra normal)"),
            ColunaView("doc_financeiro", "número da duplicata gerada"),
            ColunaView("numero_titulo", "número do título a pagar"),
            ColunaView("parcela_titulo", "número da parcela do título"),
            ColunaView(
                "data_emissao_original",
                "data de emissão do título a pagar",
                formato_data_texto=_FORMATO_DATA_BR,
            ),
            ColunaView(
                "data_vencimento_original",
                "data de vencimento do título a pagar",
                formato_data_texto=_FORMATO_DATA_BR,
            ),
            ColunaView("valor_original_titulo", "valor original do título, já convertido pra moeda corrente"),
            ColunaView("valor_bruto_nf", "valor bruto da nota fiscal"),
            ColunaView("moeda_titulo", "moeda do título, formato 'codigo-nome' (ex: '1-REAL')"),
            ColunaView("taxa_moeda_origem", "taxa de câmbio na emissão do título"),
            ColunaView("taxa_data_emissao_nf", "taxa de câmbio na data de emissão da nota"),
            ColunaView("valor_moeda_titulo", "valor do título na moeda original dele"),
            ColunaView("valor_reais_titulo", "valor do título em reais"),
            ColunaView("saldo_moeda_titulo", "saldo em aberto na moeda original do título"),
            ColunaView(
                "saldo_aberto",
                "valor numérico do saldo em aberto em reais — NÃO é um flag/booleano. "
                "0 = título já quitado; qualquer valor MAIOR QUE 0 = título em aberto "
                "(use 'saldo_aberto > 0', nunca 'saldo_aberto = 1')",
            ),
        ),
        fonte="protheus",
    ),
    ViewFinanceira(
        nome="vwia_devolucoes_compra",
        descricao="Devolução de mercadoria ao fornecedor até o título gerado — sem dado de baixa (ver vwia_baixas_pagar).",
        colunas=(
            ColunaView("filial", "código da filial"),
            ColunaView(
                "data_emissao_origem_compra",
                "data de emissão da compra original que está sendo devolvida",
                formato_data_texto=_FORMATO_DATA_BR,
            ),
            ColunaView("numero_nota_origem", "número da nota de compra original"),
            ColunaView("serie_origem", "série da nota de compra original"),
            ColunaView(
                "data_emissao", "data de emissão desta devolução", formato_data_texto=_FORMATO_DATA_BR
            ),
            ColunaView(
                "nota",
                "número desta nota fiscal de devolução",
                tipo_filtro="texto-numerico",
            ),
            ColunaView("serie", "série desta nota fiscal de devolução"),
            ColunaView("natureza_codigo", "código da natureza financeira"),
            ColunaView("natureza_descricao", "descrição da natureza financeira"),
            ColunaView("fornecedor_codigo", "código do fornecedor + loja, formato 'codigo - loja'"),
            ColunaView("fornecedor_nome", "razão social do fornecedor"),
            ColunaView("prefixo", "prefixo do título gerado pela devolução"),
            ColunaView("tipo", "tipo do título (sempre 'NDF' nesta view — nota de débito ao fornecedor)"),
            ColunaView("doc_financeiro", "número da duplicata gerada"),
            ColunaView("numero_titulo", "número do título gerado pela devolução"),
            ColunaView("parcela_titulo", "número da parcela do título"),
            ColunaView(
                "data_emissao_original", "data de emissão do título", formato_data_texto=_FORMATO_DATA_BR
            ),
            ColunaView(
                "data_vencimento_original",
                "data de vencimento do título",
                formato_data_texto=_FORMATO_DATA_BR,
            ),
            ColunaView("valor_original_titulo", "valor original do título, já convertido pra moeda corrente"),
            ColunaView("valor_bruto_nf", "valor bruto da nota fiscal de devolução"),
            ColunaView("moeda_titulo", "moeda do título, formato 'codigo-nome' (ex: '1-REAL')"),
            ColunaView("taxa_moeda_origem", "taxa de câmbio na emissão do título"),
            ColunaView("taxa_data_emissao_nf", "taxa de câmbio na data de emissão da nota"),
            ColunaView("valor_moeda_titulo", "valor do título na moeda original dele"),
            ColunaView("valor_reais_titulo", "valor do título em reais"),
            ColunaView("saldo_moeda_titulo", "saldo em aberto na moeda original do título"),
            ColunaView(
                "saldo_aberto",
                "valor numérico do saldo em aberto em reais — NÃO é um flag/booleano. "
                "0 = título já quitado; qualquer valor MAIOR QUE 0 = título em aberto "
                "(use 'saldo_aberto > 0', nunca 'saldo_aberto = 1')",
            ),
        ),
        fonte="protheus",
    ),
    ViewFinanceira(
        nome="vwia_baixas_pagar",
        descricao=(
            "Baixas (pagamentos) de títulos a pagar — uma linha por baixa. Combine com "
            "vwia_notas_compra ou vwia_devolucoes_compra (mesma filial/prefixo/número/parcela/"
            "tipo/fornecedor) pra ver o título de origem."
        ),
        colunas=(
            ColunaView("filial", "código da filial"),
            ColunaView("prefixo", "prefixo do título baixado"),
            ColunaView("numero_titulo", "número do título baixado"),
            ColunaView("parcela_titulo", "número da parcela baixada"),
            ColunaView("tipo", "tipo do título baixado ('NF' = compra normal, 'NDF' = devolução)"),
            ColunaView("fornecedor_codigo", "código do fornecedor + loja, formato 'codigo - loja'"),
            ColunaView(
                "seq_baixa",
                "sequência da baixa (um título pode ter mais de uma baixa parcial), a partir de 1",
            ),
            ColunaView("tipo_doc_baixa", "código do tipo de documento da baixa (ex: 'CH', 'TR', 'DC')"),
            ColunaView("desc_tipo_doc_baixa", "descrição por extenso do tipo de documento da baixa"),
            ColunaView(
                "data_baixa",
                "data em que o título foi efetivamente pago",
                formato_data_texto=_FORMATO_DATA_BR,
            ),
            ColunaView("taxa_data_baixa", "taxa de câmbio na data da baixa"),
            ColunaView("valor_baixado_moeda", "valor baixado (pago) na moeda original do título"),
            ColunaView("valor_baixado_reais", "valor baixado (pago) em reais"),
            ColunaView("valor_juros_baixa", "valor de juros pago por atraso nessa baixa (0 se não houve)"),
            ColunaView("valor_multa_baixa", "valor de multa paga por atraso nessa baixa (0 se não houve)"),
            ColunaView("valor_correcao_baixa", "valor de correção monetária nessa baixa (0 se não houve)"),
            ColunaView("valor_desconto_baixa", "valor de desconto obtido nessa baixa (0 se não houve)"),
            ColunaView("valor_liquido_baixa", "valor líquido efetivamente pago nessa baixa"),
            ColunaView("motivo_baixa", "código do motivo da baixa"),
            ColunaView("banco_baixa", "código do banco usado na baixa"),
            ColunaView("agencia_baixa", "agência bancária usada na baixa"),
            ColunaView("conta_baixa", "conta bancária usada na baixa"),
            ColunaView("documento_baixa", "número do documento da baixa (ex: número do cheque)"),
            ColunaView("recibo_baixa", "número do recibo da baixa"),
            ColunaView("historico_baixa", "descrição/histórico livre da baixa"),
        ),
        relacionamentos=(
            RelacionamentoView(
                view_destino="vwia_notas_compra",
                colunas_locais=(
                    "filial",
                    "prefixo",
                    "numero_titulo",
                    "parcela_titulo",
                    "tipo",
                    "fornecedor_codigo",
                ),
                colunas_destino=(
                    "filial",
                    "prefixo",
                    "numero_titulo",
                    "parcela_titulo",
                    "tipo",
                    "fornecedor_codigo",
                ),
                descricao="Título de compra normal que essa baixa quitou (parcial ou totalmente).",
            ),
            RelacionamentoView(
                view_destino="vwia_devolucoes_compra",
                colunas_locais=(
                    "filial",
                    "prefixo",
                    "numero_titulo",
                    "parcela_titulo",
                    "tipo",
                    "fornecedor_codigo",
                ),
                colunas_destino=(
                    "filial",
                    "prefixo",
                    "numero_titulo",
                    "parcela_titulo",
                    "tipo",
                    "fornecedor_codigo",
                ),
                descricao="Título de devolução (NDF) que essa baixa quitou (parcial ou totalmente).",
            ),
        ),
        fonte="protheus",
    ),
)

NOMES_VIEWS_PERMITIDAS: frozenset[str] = frozenset(view.nome.upper() for view in VIEWS_DISPONIVEIS)

_PALAVRAS_NUMERICAS = ("valor", "quantidade", "saldo", "preco", "preço", "custo")


def inferir_tipo_filtro(coluna: ColunaView) -> str:
    """Tipo de filtro pra uma coluna — usado tanto pra escolher o widget
    certo na tela "Criar Relatório" quanto pra montar a cláusula certa no
    backend (`relatorio_customizado_sql.py::_montar_sql`).

    Usa `coluna.tipo_filtro` quando declarado explicitamente (ver docstring
    de `ColunaView`) — só cai na heurística por nome quando não há
    override: colunas "data_*" viram filtro de período, colunas com
    palavras que indicam valor numérico viram filtro de faixa (min/máx), o
    resto vira filtro de texto (lista de valores exatos)."""
    if coluna.tipo_filtro is not None:
        return coluna.tipo_filtro
    if coluna.nome.startswith("data_"):
        return "periodo-data"
    if any(palavra in coluna.nome for palavra in _PALAVRAS_NUMERICAS):
        return "numero"
    return "texto"
