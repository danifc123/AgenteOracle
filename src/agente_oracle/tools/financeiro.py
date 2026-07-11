from datetime import datetime

from agente_oracle.db.connection import get_connection
from agente_oracle.relatorios import gerar_xlsx

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


def _linha_relatorio(row: tuple) -> list:
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
        float(valor),
        nome_conta,
        banco,
        nome_categoria,
        tipo_categoria,
        nome_entidade,
        tipo_entidade,
    ]


def listar_transacoes_json(limite: int = 20) -> list[dict]:
    """Lista as transações financeiras mais recentes, unindo (INNER JOIN) a conta
    bancária, a categoria financeira e o fornecedor/cliente de cada lançamento, no
    formato usado pela tabela do frontend."""
    rows = _buscar_transacoes(limite)
    return [
        {
            "idTransacao": id_transacao,
            "descricao": descricao,
            "valor": float(valor),
            "dataTransacao": data_transacao.strftime("%Y-%m-%d"),
            "tipoTransacao": tipo_transacao,
            "statusTransacao": status_transacao,
            "conta": {"nomeConta": nome_conta, "banco": banco},
            "categoria": {"nomeCategoria": nome_categoria, "tipoCategoria": tipo_categoria},
            "entidade": {"nome": nome_entidade, "tipoEntidade": tipo_entidade},
        }
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
        ) in rows
    ]


def exportar_transacoes_xlsx(limite: int = 20) -> tuple[bytes, str]:
    """Gera o mesmo relatório de transações em memória como um arquivo Excel
    (.xlsx), no mesmo formato usado pelos relatórios gerados pela IA no chat,
    para download direto pelo navegador."""
    rows = _buscar_transacoes(limite)
    conteudo_xlsx = gerar_xlsx(_CABECALHO, [_linha_relatorio(row) for row in rows], titulo="Transações")
    nome_arquivo = f"transacoes_financeiras_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    return conteudo_xlsx, nome_arquivo
