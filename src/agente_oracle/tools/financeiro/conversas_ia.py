"""Trilha de auditoria das conversas de IA — mesmo padrão de
`tools/auth/eventos_seguranca.py` (`CREATE TABLE IF NOT EXISTS`, sem
migração separada, escrita best-effort). Existe porque hoje nenhuma
conversa fica registrada em lugar nenhum: se um dado errado for mostrado ou
alguém tentar um jailbreak no chat, não tem como reconstruir depois o que
foi perguntado, qual SQL rodou e o que a IA respondeu.

Tem coluna `modulo` (default `'financeiro'`) já pensando num futuro chat de
RH/Estoque usando essa mesma tabela, sem precisar de `ALTER TABLE` depois —
mesmo truque de `tools/financeiro/historico.py` (`relatorios_historico`).
"""

import json
from datetime import UTC, datetime
from typing import Any

from agente_oracle.db.connection import DatabaseError, get_postgres_connection

_tabela_garantida = False


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversas_ia (
            id BIGSERIAL PRIMARY KEY,
            modulo VARCHAR NOT NULL DEFAULT 'financeiro',
            usuario VARCHAR NOT NULL,
            mensagem_usuario TEXT NOT NULL,
            sql_gerado TEXT,
            resposta_final TEXT,
            eventos JSONB,
            criado_em TIMESTAMPTZ NOT NULL
        )
    """)
    _tabela_garantida = True


def listar(limite: int = 200) -> list[dict]:
    """Últimas conversas registradas, mais recentes primeiro — sem tela no
    frontend ainda (uso hoje é só investigar um incidente direto no banco),
    mas já serve pra `tests/integration/conftest.py` garantir que a tabela
    existe antes do checkpoint de limpeza, mesmo padrão de
    `eventos_seguranca.listar`."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            SELECT id, modulo, usuario, mensagem_usuario, sql_gerado, resposta_final, eventos, criado_em
            FROM conversas_ia ORDER BY id DESC LIMIT :limite
            """,
            limite=limite,
        )
        linhas = cursor.fetchall()

    return [
        {
            "id": id_,
            "modulo": modulo,
            "usuario": usuario,
            "mensagem_usuario": mensagem_usuario,
            "sql_gerado": sql_gerado,
            "resposta_final": resposta_final,
            "eventos": json.loads(eventos) if isinstance(eventos, str) else eventos,
            "criado_em": criado_em.isoformat(),
        }
        for id_, modulo, usuario, mensagem_usuario, sql_gerado, resposta_final, eventos, criado_em in linhas
    ]


def registrar(
    usuario: str,
    mensagem_usuario: str,
    resposta_final: str,
    eventos: list[dict[str, Any]],
) -> None:
    """Grava um turno de conversa na trilha. Nunca levanta erro pra quem
    chamou — mesma garantia de `eventos_seguranca.registrar`: uma falha ao
    GRAVAR a auditoria não pode derrubar a resposta do chat, que já foi
    calculada com sucesso nesse ponto."""
    try:
        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute(
                """
                INSERT INTO conversas_ia (usuario, mensagem_usuario, sql_gerado, resposta_final, eventos, criado_em)
                VALUES (:usuario, :mensagem_usuario, :sql_gerado, :resposta_final, :eventos::jsonb, :criado_em)
                """,
                usuario=usuario,
                mensagem_usuario=mensagem_usuario,
                sql_gerado=_ultimo_sql_dos_eventos(eventos),
                resposta_final=resposta_final,
                eventos=json.dumps(eventos),
                criado_em=datetime.now(UTC),
            )
    except DatabaseError:
        pass


def _ultimo_sql_dos_eventos(eventos: list[dict[str, Any]]) -> str | None:
    """Pega o SQL do último evento de consulta do turno (quando teve
    consulta) — usado só pra facilitar a leitura da trilha depois, o
    detalhe completo continua disponível na coluna `eventos`."""
    for evento in reversed(eventos):
        sql = evento.get("argumentos", {}).get("sql")
        if sql:
            return sql
    return None
