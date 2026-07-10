from agente_oracle.db.connection import get_connection


def listar_transacoes_financeiras(limite: int = 20) -> str:
    """Lista as transações financeiras mais recentes, unindo (INNER JOIN) a conta
    bancária, a categoria financeira e o fornecedor/cliente de cada lançamento.
    """
    query = """
        SELECT
            t.ID_TRANSACAO,
            t.DESCRICAO,
            t.TIPO_TRANSACAO,
            t.VALOR,
            t.DATA_TRANSACAO,
            t.STATUS_TRANSACAO,
            c.NOME_CONTA,
            c.BANCO,
            cat.NOME_CATEGORIA,
            cat.TIPO_CATEGORIA,
            fc.NOME AS NOME_ENTIDADE,
            fc.TIPO_ENTIDADE
        FROM TRANSACOES t
        INNER JOIN CONTAS_BANCARIAS c ON c.ID_CONTA = t.ID_CONTA
        INNER JOIN CATEGORIAS_FINANCEIRAS cat ON cat.ID_CATEGORIA = t.ID_CATEGORIA
        INNER JOIN FORNECEDORES_CLIENTES fc ON fc.ID_ENTIDADE = t.ID_ENTIDADE
        ORDER BY t.DATA_TRANSACAO DESC
        FETCH FIRST :limite ROWS ONLY
    """

    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(query, limite=limite)
        rows = cursor.fetchall()

    if not rows:
        return "Nenhuma transação encontrada."

    linhas = []
    for (
        id_transacao,
        descricao,
        tipo_transacao,
        valor,
        data_transacao,
        status_transacao,
        nome_conta,
        banco,
        nome_categoria,
        tipo_categoria,
        nome_entidade,
        tipo_entidade,
    ) in rows:
        linhas.append(
            f"#{id_transacao} | {data_transacao:%d/%m/%Y} | {tipo_transacao} | "
            f"R$ {valor:.2f} | {status_transacao} | {descricao} | "
            f"Conta: {nome_conta} ({banco}) | Categoria: {nome_categoria} ({tipo_categoria}) | "
            f"{tipo_entidade}: {nome_entidade}"
        )

    return "\n".join(linhas)
