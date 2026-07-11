import re
from datetime import date, datetime
from decimal import Decimal

from agente_oracle.db.connection import get_connection

TABELAS_PERMITIDAS = {
    "TRANSACOES",
    "CONTAS_BANCARIAS",
    "CATEGORIAS_FINANCEIRAS",
    "FORNECEDORES_CLIENTES",
    "FATURAS",
}

PALAVRAS_BLOQUEADAS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "MERGE",
    "GRANT",
    "REVOKE",
    "CREATE",
    "EXECUTE IMMEDIATE",
    "CALL ",
    "BEGIN",
    "DECLARE",
    "UTL_",
    "DBMS_",
    "PRAGMA",
)

_TABELA_REGEX = re.compile(r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)

LIMITE_MAXIMO_LINHAS = 200
TIMEOUT_MS = 10_000


class ConsultaFinanceiraInvalida(Exception):
    """Levantada quando o SQL gerado pela IA não passa nas validações de segurança."""


def _validar_consulta(sql: str) -> str:
    sql_limpo = sql.strip().rstrip(";").strip()

    if not sql_limpo:
        raise ConsultaFinanceiraInvalida("A consulta está vazia.")

    if ";" in sql_limpo:
        raise ConsultaFinanceiraInvalida("Apenas uma única instrução é permitida (sem ';' no meio da consulta).")

    if not re.match(r"^\s*SELECT\b", sql_limpo, re.IGNORECASE):
        raise ConsultaFinanceiraInvalida("Somente instruções SELECT são permitidas.")

    sql_upper = sql_limpo.upper()
    for palavra in PALAVRAS_BLOQUEADAS:
        if palavra in sql_upper:
            raise ConsultaFinanceiraInvalida(f"A consulta contém um termo não permitido: '{palavra.strip()}'.")

    tabelas_usadas = {t.upper() for t in _TABELA_REGEX.findall(sql_limpo)}
    if not tabelas_usadas:
        raise ConsultaFinanceiraInvalida("Não foi possível identificar as tabelas usadas na consulta.")

    tabelas_nao_permitidas = tabelas_usadas - TABELAS_PERMITIDAS
    if tabelas_nao_permitidas:
        raise ConsultaFinanceiraInvalida(
            f"A consulta referencia tabela(s) não permitida(s): {', '.join(sorted(tabelas_nao_permitidas))}."
        )

    if "FETCH FIRST" not in sql_upper and "ROWNUM" not in sql_upper:
        sql_limpo = f"{sql_limpo}\nFETCH FIRST {LIMITE_MAXIMO_LINHAS} ROWS ONLY"

    return sql_limpo


def _serializar(valor):
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def executar_consulta_financeira(sql: str) -> list[dict]:
    """Executa uma consulta SELECT sobre as tabelas financeiras do Oracle
    (TRANSACOES, CONTAS_BANCARIAS, CATEGORIAS_FINANCEIRAS, FORNECEDORES_CLIENTES,
    FATURAS) e devolve as linhas encontradas.

    Use esta ferramenta quando o usuário pedir um relatório ou dado que não é
    coberto por nenhuma ferramenta pronta. Regras: gere sempre SQL Oracle válido
    e somente SELECT; nunca use INSERT/UPDATE/DELETE ou comandos DDL; use apenas
    as tabelas financeiras listadas acima, combinando com JOIN quando precisar
    relacionar dados; nunca invente colunas ou tabelas fora do esquema conhecido.
    """
    sql_validado = _validar_consulta(sql)

    with get_connection() as connection:
        connection.call_timeout = TIMEOUT_MS
        cursor = connection.cursor()
        cursor.execute(sql_validado)
        colunas = [descricao[0] for descricao in cursor.description]
        linhas = cursor.fetchall()

    return [dict(zip(colunas, (_serializar(valor) for valor in linha))) for linha in linhas]
