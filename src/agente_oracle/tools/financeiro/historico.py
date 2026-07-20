"""Histórico de relatórios gerados pela IA — guardado numa tabela no mesmo
banco relacional configurado em DB_BACKEND (Postgres localmente), em vez de
um serviço externo (era MongoDB Atlas antes; trocado por não conectar de
forma confiável no ambiente do time).

A tabela é criada sozinha na primeira chamada (`CREATE TABLE IF NOT EXISTS`),
sem precisar de uma migração separada. Como não há um worker rodando em
background, o TTL de 15h (`TEMPO_EXPIRACAO`) não é feito por um processo que
varre e apaga sozinho como o índice TTL do Mongo fazia — em vez disso:
- toda leitura (`buscar_por_sql`, `listar`) já filtra `expira_em > now()`,
  então um relatório expirado nunca aparece pro usuário, mesmo que a linha
  ainda exista fisicamente na tabela;
- `salvar` aproveita a própria escrita pra limpar fisicamente as linhas não
  fixadas já expiradas, então a tabela não cresce sem limite.

As funções públicas deste módulo (`hash_sql`, `buscar_por_sql`, `salvar`,
`listar`, `obter`, `deletar`, `fixar`, `desfixar`) têm a mesma assinatura e
devolvem o mesmo formato de dicionário de antes (chave `_id` incluída, por
compatibilidade com `server/financeiro/historico.py` e
`tools/financeiro/consulta_livre.py` — nenhum dos dois precisou mudar nessa
troca).
"""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from agente_oracle.db.connection import get_connection

_SELECT_FROM_REGEX = re.compile(r"^SELECT\s+(.*?)\s+FROM\s", re.IGNORECASE | re.DOTALL)

TEMPO_EXPIRACAO = timedelta(hours=15)

_COLUNAS_COMPLETAS = "id, hash_sql, sql, titulo, colunas, linhas, total_linhas, criado_em, fixado, expira_em"

_tabela_garantida = False


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS relatorios_historico (
            id BIGSERIAL PRIMARY KEY,
            hash_sql VARCHAR NOT NULL UNIQUE,
            sql TEXT NOT NULL,
            titulo VARCHAR NOT NULL,
            colunas JSONB NOT NULL,
            linhas JSONB NOT NULL,
            total_linhas INTEGER NOT NULL,
            criado_em TIMESTAMPTZ NOT NULL,
            fixado BOOLEAN NOT NULL DEFAULT FALSE,
            expira_em TIMESTAMPTZ
        )
    """)
    _tabela_garantida = True


def hash_sql(sql_validado: str) -> str:
    """Normaliza o SQL para uma forma canônica e gera um hash estável, usado
    como chave de deduplicação: dois SQLs equivalentes (mesmas colunas em
    ordem diferente, espaçamento ou maiúsculas/minúsculas diferentes) geram o
    mesmo hash. Não altera o SQL que de fato roda no banco — só a versão
    usada para comparação."""
    sql_normalizado = " ".join(sql_validado.split()).upper()

    correspondencia = _SELECT_FROM_REGEX.match(sql_normalizado)
    if correspondencia:
        colunas = sorted(coluna.strip() for coluna in correspondencia.group(1).split(","))
        sql_normalizado = (
            sql_normalizado[: correspondencia.start(1)]
            + ", ".join(colunas)
            + sql_normalizado[correspondencia.end(1) :]
        )

    return hashlib.sha256(sql_normalizado.encode("utf-8")).hexdigest()


def _carregar_json(valor):
    return json.loads(valor) if isinstance(valor, str) else valor


def _linha_para_documento(linha: tuple) -> dict:
    id_, hash_sql_valor, sql, titulo, colunas, linhas, total_linhas, criado_em, fixado, expira_em = linha
    return {
        "_id": id_,
        "hash_sql": hash_sql_valor,
        "sql": sql,
        "titulo": titulo,
        "colunas": _carregar_json(colunas),
        "linhas": _carregar_json(linhas),
        "total_linhas": total_linhas,
        "criado_em": criado_em,
        "fixado": fixado,
        "expira_em": expira_em,
    }


def buscar_por_sql(sql_validado: str) -> dict | None:
    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            f"""
            SELECT {_COLUNAS_COMPLETAS} FROM relatorios_historico
            WHERE hash_sql = :hash_sql AND (fixado = TRUE OR expira_em > now())
            """,
            hash_sql=hash_sql(sql_validado),
        )
        linha = cursor.fetchone()
    return _linha_para_documento(linha) if linha else None


def salvar(sql_validado: str, titulo: str, colunas: list[str], linhas: list[list]) -> dict:
    """Salva um relatório novo no histórico. Se outra chamada concorrente já
    tiver salvo o mesmo SQL entre a busca e este insert, devolve o documento
    já existente em vez de duplicar (a constraint única em hash_sql garante
    isso). Por padrão, o relatório expira e é "esquecido" após
    TEMPO_EXPIRACAO — a menos que seja fixado (veja `fixar`)."""
    agora = datetime.now(timezone.utc)
    hash_valor = hash_sql(sql_validado)

    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)

        # Aproveita a escrita pra limpar fisicamente o que já expirou e não
        # está fixado — não tem worker rodando em background pra isso aqui.
        cursor.execute("DELETE FROM relatorios_historico WHERE fixado = FALSE AND expira_em <= now()")

        cursor.execute(
            f"""
            INSERT INTO relatorios_historico
                (hash_sql, sql, titulo, colunas, linhas, total_linhas, criado_em, fixado, expira_em)
            VALUES
                (:hash_sql, :sql_texto, :titulo, :colunas::jsonb, :linhas::jsonb, :total_linhas, :criado_em, FALSE, :expira_em)
            ON CONFLICT (hash_sql) DO NOTHING
            RETURNING {_COLUNAS_COMPLETAS}
            """,
            hash_sql=hash_valor,
            sql_texto=sql_validado,
            titulo=titulo,
            colunas=json.dumps(colunas),
            linhas=json.dumps(linhas),
            total_linhas=len(linhas),
            criado_em=agora,
            expira_em=agora + TEMPO_EXPIRACAO,
        )
        linha = cursor.fetchone()

        if linha is None:
            cursor.execute(
                f"SELECT {_COLUNAS_COMPLETAS} FROM relatorios_historico WHERE hash_sql = :hash_sql",
                hash_sql=hash_valor,
            )
            linha = cursor.fetchone()

    return _linha_para_documento(linha)


def listar() -> list[dict]:
    """Lista os relatórios salvos, do mais recente para o mais antigo, sem os
    dados completos das linhas (usado pela tela de histórico). Relatórios não
    fixados que já passaram do prazo de expiração não aparecem, mesmo que a
    limpeza física ainda não tenha rodado."""
    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("""
            SELECT id, hash_sql, sql, titulo, colunas, total_linhas, criado_em, fixado, expira_em
            FROM relatorios_historico
            WHERE fixado = TRUE OR expira_em > now()
            ORDER BY criado_em DESC
        """)
        linhas_resultado = cursor.fetchall()

    return [
        {
            "_id": linha[0],
            "hash_sql": linha[1],
            "sql": linha[2],
            "titulo": linha[3],
            "colunas": _carregar_json(linha[4]),
            "total_linhas": linha[5],
            "criado_em": linha[6],
            "fixado": linha[7],
            "expira_em": linha[8],
        }
        for linha in linhas_resultado
    ]


def obter(id_relatorio: str) -> dict | None:
    try:
        id_numerico = int(id_relatorio)
    except ValueError:
        return None

    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            f"SELECT {_COLUNAS_COMPLETAS} FROM relatorios_historico WHERE id = :id",
            id=id_numerico,
        )
        linha = cursor.fetchone()
    return _linha_para_documento(linha) if linha else None


def deletar(id_relatorio: str) -> bool:
    try:
        id_numerico = int(id_relatorio)
    except ValueError:
        return False

    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("DELETE FROM relatorios_historico WHERE id = :id", id=id_numerico)
        return cursor.rowcount > 0


def fixar(id_relatorio: str) -> bool:
    """Fixa um relatório: ele deixa de expirar (`expira_em` vira NULL)."""
    try:
        id_numerico = int(id_relatorio)
    except ValueError:
        return False

    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "UPDATE relatorios_historico SET fixado = TRUE, expira_em = NULL WHERE id = :id",
            id=id_numerico,
        )
        return cursor.rowcount > 0


def desfixar(id_relatorio: str) -> bool:
    """Desfixa um relatório: ele volta a expirar, com um novo prazo de
    TEMPO_EXPIRACAO a partir de agora."""
    try:
        id_numerico = int(id_relatorio)
    except ValueError:
        return False

    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "UPDATE relatorios_historico SET fixado = FALSE, expira_em = :expira_em WHERE id = :id",
            id=id_numerico,
            expira_em=datetime.now(timezone.utc) + TEMPO_EXPIRACAO,
        )
        return cursor.rowcount > 0
