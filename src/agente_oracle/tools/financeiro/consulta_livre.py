import re
from datetime import date, datetime
from decimal import Decimal

from agente_oracle.agent.financeiro.schema import NOMES_VIEWS_PERMITIDAS
from agente_oracle.db.connection import DatabaseError, eh_erro_coluna_invalida, get_connection
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.tools.financeiro import historico

# Mesma lista de views usada no prompt do agente (agent/financeiro/schema.py) —
# fonte única, pra nunca ficar um SQL que o prompt promete mas a validação
# rejeita (ou o contrário). Vazio até as views financeiras existirem no banco,
# então toda consulta é rejeitada enquanto isso.
TABELAS_PERMITIDAS: frozenset[str] = NOMES_VIEWS_PERMITIDAS

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
            "Não é possível gerar esse relatório: a consulta usa dado(s) fora do escopo "
            "financeiro autorizado para este agente."
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


def _executar(sql_validado: str) -> tuple[list[str], list[tuple]]:
    try:
        with get_connection() as connection:
            connection.call_timeout = TIMEOUT_MS
            cursor = connection.cursor()
            cursor.execute(sql_validado)
            colunas = [descricao[0] for descricao in cursor.description]
            linhas = cursor.fetchall()
    except DatabaseError as erro:
        mensagem_erro = str(erro).strip()
        if eh_erro_coluna_invalida(erro):
            raise ConsultaFinanceiraInvalida(
                "Não é possível gerar esse relatório: a consulta faz referência a uma coluna "
                "ou junção que não existe no banco — as tabelas pedidas não têm uma relação "
                "direta entre si."
            ) from erro
        raise ConsultaFinanceiraInvalida(
            f"Não foi possível executar a consulta no banco ({mensagem_erro})."
        ) from erro

    return colunas, linhas


def _executar_com_cache(sql: str, titulo: str) -> tuple[list[str], list[list], str, bool, datetime]:
    """Valida o SQL e, se um relatório idêntico já estiver salvo no histórico
    (mesmo SQL, normalizado), reaproveita o resultado salvo em vez de rodar de
    novo no Oracle. Caso contrário, executa e salva no histórico para a
    próxima vez. Devolve (colunas, linhas, titulo, reutilizado, criado_em)."""
    sql_validado = _validar_consulta(sql)

    existente = historico.buscar_por_sql(sql_validado)
    if existente is not None:
        return existente["colunas"], existente["linhas"], existente["titulo"], True, existente["criado_em"]

    colunas, linhas_brutas = _executar(sql_validado)
    linhas = [[_serializar(valor) for valor in linha] for linha in linhas_brutas]

    documento = historico.salvar(sql_validado, titulo, colunas, linhas)
    return documento["colunas"], documento["linhas"], documento["titulo"], False, documento["criado_em"]


def executar_consulta_financeira(sql: str, titulo: str) -> dict:
    """Executa uma consulta SELECT sobre as tabelas financeiras do banco configurado
    e devolve as linhas encontradas.

    Use esta ferramenta quando o usuário pedir um relatório ou dado que não é
    coberto por nenhuma ferramenta pronta. Regras: gere sempre SQL válido para o
    banco configurado e somente SELECT; nunca use INSERT/UPDATE/DELETE ou comandos DDL; use apenas
    as tabelas financeiras liberadas para este agente, combinando com JOIN quando precisar
    relacionar dados; nunca invente colunas ou tabelas fora do esquema conhecido.
    Informe também um `titulo` curto e claro, em português, descrevendo o que o
    relatório mostra (ex: "Transações de fornecedor X em março de 2026") — ele é
    salvo no histórico de relatórios.

    Se um relatório com exatamente o mesmo SQL já tiver sido gerado antes, esta
    ferramenta NÃO roda a consulta de novo no banco: devolve o resultado salvo
    no histórico, com `reutilizado=true` e `gerado_em` indicando quando foi
    gerado originalmente.
    """
    colunas, linhas, titulo_final, reutilizado, criado_em = _executar_com_cache(sql, titulo)
    return {
        "reutilizado": reutilizado,
        "titulo": titulo_final,
        "gerado_em": criado_em.isoformat(),
        "dados": [dict(zip(colunas, linha)) for linha in linhas],
    }


def exportar_consulta_financeira_xlsx(sql: str) -> bytes:
    """Roda a mesma consulta validada (SELECT, tabelas financeiras permitidas) —
    ou reaproveita o resultado do histórico, se já tiver sido gerada antes — e
    monta um arquivo Excel (.xlsx) em memória com o resultado, para download."""
    colunas, linhas, _titulo, _reutilizado, _criado_em = _executar_com_cache(sql, titulo="Relatório")
    return gerar_xlsx(colunas, linhas, titulo="Relatório")
