"""Achados de auditoria que um usuário já revisou e marcou como "não é
problema" — guardados numa tabela no mesmo banco relacional configurado em
DB_BACKEND, criada sozinha na primeira chamada (`CREATE TABLE IF NOT
EXISTS`), sem precisar de migração separada — mesmo padrão de
`tools/financeiro/historico.py`. A dispensa é por usuário: cada achado é
identificado pela tupla (módulo, view, campo, valor) que a IA já devolve,
sem precisar de um id sintético."""

from datetime import UTC, datetime

from agente_oracle.db.connection import get_connection

_tabela_garantida = False


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auditoria_dispensados (
            id BIGSERIAL PRIMARY KEY,
            usuario_id VARCHAR NOT NULL,
            modulo VARCHAR NOT NULL,
            view_nome VARCHAR NOT NULL,
            campo VARCHAR NOT NULL,
            valor VARCHAR NOT NULL,
            dispensado_em TIMESTAMPTZ NOT NULL,
            UNIQUE (usuario_id, modulo, view_nome, campo, valor)
        )
    """)
    _tabela_garantida = True


def dispensar(usuario_id: str, modulo: str, view: str, campo: str, valor: str) -> None:
    """Marca um achado como dispensado para este usuário. Se ele já tiver
    dispensado exatamente o mesmo achado antes, não faz nada (a constraint
    única evita duplicar)."""
    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            INSERT INTO auditoria_dispensados (usuario_id, modulo, view_nome, campo, valor, dispensado_em)
            VALUES (:usuario_id, :modulo, :view_nome, :campo, :valor, :dispensado_em)
            ON CONFLICT (usuario_id, modulo, view_nome, campo, valor) DO NOTHING
            """,
            usuario_id=usuario_id,
            modulo=modulo,
            view_nome=view,
            campo=campo,
            valor=valor,
            dispensado_em=datetime.now(UTC),
        )


def listar_dispensados(usuario_id: str) -> set[tuple[str, str, str, str]]:
    """Achados (modulo, view, campo, valor) já dispensados por este usuário —
    usado para filtrar a lista de achados antes de devolver ao front."""
    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "SELECT modulo, view_nome, campo, valor FROM auditoria_dispensados WHERE usuario_id = :usuario_id",
            usuario_id=usuario_id,
        )
        linhas = cursor.fetchall()
    return {(modulo, view, campo, valor) for modulo, view, campo, valor in linhas}
