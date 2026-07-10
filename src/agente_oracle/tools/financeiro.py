import csv
from datetime import datetime
from pathlib import Path

from agente_oracle.db.connection import get_connection

EXPORTS_DIR = Path("exports")


def listar_transacoes_financeiras(limite: int = 20) -> str:
    """Lista as transações financeiras mais recentes, unindo (INNER JOIN) a conta
    bancária, a categoria financeira e o fornecedor/cliente de cada lançamento, e
    exporta o resultado em um arquivo CSV organizado e com uma tabela persolanizada com os dados.
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

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    caminho_arquivo = EXPORTS_DIR / f"transacoes_financeiras_{datetime.now():%Y%m%d_%H%M%S}.csv"

    cabecalho = [
        "ID_TRANSACAO",
        "DATA_TRANSACAO",
        "TIPO_TRANSACAO",
        "STATUS_TRANSACAO",
        "DESCRICAO",
        "VALOR",
        "CONTA",
        "BANCO",
        "CATEGORIA",
        "TIPO_CATEGORIA",
        "ENTIDADE",
        "TIPO_ENTIDADE",
    ]

    with caminho_arquivo.open("w", newline="", encoding="utf-8-sig") as arquivo_csv:
        escritor = csv.writer(arquivo_csv, delimiter=";")
        escritor.writerow(cabecalho)
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
            escritor.writerow(
                [
                    id_transacao,
                    data_transacao.strftime("%d/%m/%Y"),
                    tipo_transacao,
                    status_transacao,
                    descricao,
                    f"{valor:.2f}",
                    nome_conta,
                    banco,
                    nome_categoria,
                    tipo_categoria,
                    nome_entidade,
                    tipo_entidade,
                ]
            )

    return f"Exportação concluída: {len(rows)} transação(ões) salvas em {caminho_arquivo.resolve()}"
