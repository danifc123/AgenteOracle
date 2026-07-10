import csv
import io
from datetime import datetime
from pathlib import Path

from agente_oracle.db.connection import get_connection

EXPORTS_DIR = Path("exports")

_QUERY = """
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

_CABECALHO = [
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


def _buscar_transacoes(limite: int) -> list[tuple]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(_QUERY, limite=limite)
        return cursor.fetchall()


def _linha_csv(row: tuple) -> list:
    (
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
    ) = row
    return [
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


def listar_transacoes_financeiras(limite: int = 20) -> str:
    """Lista as transações financeiras mais recentes, unindo (INNER JOIN) a conta
    bancária, a categoria financeira e o fornecedor/cliente de cada lançamento, e
    exporta o resultado em um arquivo CSV organizado e com uma tabela persolanizada com os dados.
    """
    rows = _buscar_transacoes(limite)

    if not rows:
        return "Nenhuma transação encontrada."

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    caminho_arquivo = EXPORTS_DIR / f"transacoes_financeiras_{datetime.now():%Y%m%d_%H%M%S}.csv"

    with caminho_arquivo.open("w", newline="", encoding="utf-8-sig") as arquivo_csv:
        escritor = csv.writer(arquivo_csv, delimiter=";")
        escritor.writerow(_CABECALHO)
        for row in rows:
            escritor.writerow(_linha_csv(row))

    return f"Exportação concluída: {len(rows)} transação(ões) salvas em {caminho_arquivo.resolve()}"


def exportar_transacoes_csv(limite: int = 20) -> tuple[bytes, str]:
    """Gera o mesmo relatório de transações em memória (bytes CSV, com BOM utf-8
    para acentuação correta no Excel), para download direto pelo navegador."""
    rows = _buscar_transacoes(limite)

    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerow(_CABECALHO)
    for row in rows:
        escritor.writerow(_linha_csv(row))

    nome_arquivo = f"transacoes_financeiras_{datetime.now():%Y%m%d_%H%M%S}.csv"
    return (b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")), nome_arquivo
