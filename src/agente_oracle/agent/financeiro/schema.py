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

# Prefixo das tools MCP deste módulo (ex: "financeiro_executar_consulta_financeira").
# Usado tanto no registro das tools (server/financeiro/ia.py) quanto na hora de
# filtrar quais tools cada agente enxerga (agent/cli.py, server/financeiro/ia.py) —
# assim, quando outro módulo (Compras, RH...) registrar tools no mesmo servidor
# MCP, o agente do Financeiro continua só vendo e só podendo chamar as dele.
PREFIXO_TOOL: str = "financeiro_"


@dataclass(frozen=True)
class ColunaView:
    """Uma coluna de uma view financeira, com descrição curta pra IA entender o que ela guarda."""

    nome: str
    descricao: str


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
    por padrão, salvo uso de aspas)."""

    nome: str
    descricao: str
    colunas: tuple[ColunaView, ...]
    relacionamentos: tuple[RelacionamentoView, ...] = ()


VIEWS_DISPONIVEIS: tuple[ViewFinanceira, ...] = (
    ViewFinanceira(
        nome="vw_titulos_pagar",
        descricao="Títulos a pagar (contas a pagar a fornecedores), um por parcela.",
        colunas=(
            ColunaView("filial", "código da filial"),
            ColunaView("prefixo", "prefixo do documento"),
            ColunaView("numero", "número do título"),
            ColunaView("parcela", "número da parcela"),
            ColunaView("tipo", "tipo do título (ex: NF)"),
            ColunaView("fornecedor_codigo", "código do fornecedor"),
            ColunaView("fornecedor_loja", "loja do fornecedor"),
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
        ),
        relacionamentos=(
            RelacionamentoView(
                view_destino="vw_fornecedores",
                colunas_locais=("fornecedor_codigo", "fornecedor_loja"),
                colunas_destino=("codigo", "loja"),
                descricao=(
                    "Dado de fornecedor que não está aqui (cnpj_cpf, tipo_pessoa, "
                    "nome_reduzido, estado) só existe em vw_fornecedores."
                ),
            ),
        ),
    ),
    ViewFinanceira(
        nome="vw_titulos_receber",
        descricao="Títulos a receber (contas a receber de clientes), um por parcela.",
        colunas=(
            ColunaView("filial", "código da filial"),
            ColunaView("prefixo", "prefixo do documento"),
            ColunaView("numero", "número do título"),
            ColunaView("parcela", "número da parcela"),
            ColunaView("tipo", "tipo do título (ex: NF, NP)"),
            ColunaView("cliente_codigo", "código do cliente"),
            ColunaView("cliente_loja", "loja do cliente"),
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
        ),
        relacionamentos=(
            RelacionamentoView(
                view_destino="vw_clientes",
                colunas_locais=("cliente_codigo", "cliente_loja"),
                colunas_destino=("codigo", "loja"),
                descricao=(
                    "Dado de cliente que não está aqui (cnpj_cpf, tipo_pessoa, "
                    "nome_reduzido, estado) só existe em vw_clientes."
                ),
            ),
        ),
    ),
    ViewFinanceira(
        nome="vw_fornecedores",
        descricao="Cadastro de fornecedores.",
        colunas=(
            ColunaView("filial", "código da filial"),
            ColunaView(
                "codigo",
                "código do fornecedor — aqui o nome da coluna é `codigo`, NUNCA "
                "`fornecedor_codigo` (esse nome com prefixo só existe em vw_titulos_pagar).",
            ),
            ColunaView(
                "loja",
                "loja do fornecedor — aqui o nome da coluna é `loja`, NUNCA "
                "`fornecedor_loja` (esse nome com prefixo só existe em vw_titulos_pagar).",
            ),
            ColunaView("nome", "razão social / nome completo"),
            ColunaView("nome_reduzido", "nome reduzido/fantasia"),
            ColunaView("cnpj_cpf", "CNPJ ou CPF"),
            ColunaView("tipo_pessoa", "F = pessoa física, J = pessoa jurídica"),
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
        nome="vw_clientes",
        descricao="Cadastro de clientes.",
        colunas=(
            ColunaView("filial", "código da filial"),
            ColunaView(
                "codigo",
                "código do cliente — aqui o nome da coluna é `codigo`, NUNCA "
                "`cliente_codigo` (esse nome com prefixo só existe em vw_titulos_receber).",
            ),
            ColunaView(
                "loja",
                "loja do cliente — aqui o nome da coluna é `loja`, NUNCA "
                "`cliente_loja` (esse nome com prefixo só existe em vw_titulos_receber).",
            ),
            ColunaView("nome", "razão social / nome completo"),
            ColunaView("nome_reduzido", "nome reduzido/fantasia"),
            ColunaView("cnpj_cpf", "CNPJ ou CPF"),
            ColunaView("tipo_pessoa", "F = pessoa física, J = pessoa jurídica"),
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
        nome="vw_movimento_bancario",
        descricao="Movimentações bancárias (recebimentos, pagamentos e baixas) por conta.",
        colunas=(
            ColunaView("filial", "código da filial"),
            ColunaView("banco_codigo", "código do banco"),
            ColunaView("banco_nome", "nome reduzido do banco/conta"),
            ColunaView("agencia", "agência bancária"),
            ColunaView("conta", "número da conta"),
            ColunaView("data_disponivel", "data em que o valor ficou disponível na conta"),
            ColunaView("historico", "descrição/histórico do lançamento"),
            ColunaView("recebimento_pagamento", "R = recebimento, P = pagamento"),
            ColunaView("valor", "valor do lançamento"),
            ColunaView("tipo_documento", "tipo do documento (ex: RB recebimento, PG pagamento)"),
            ColunaView("conciliado", "true se o lançamento já foi conciliado com o extrato do banco"),
        ),
    ),
)

NOMES_VIEWS_PERMITIDAS: frozenset[str] = frozenset(view.nome.upper() for view in VIEWS_DISPONIVEIS)
