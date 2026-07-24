"""Cores personalizadas das categorias de relatório (as bolinhas coloridas em
"Financeiro"), por usuário — igual `tools/financeiro/layouts.py`: tabela
própria, criada sozinha (`CREATE TABLE IF NOT EXISTS`) na primeira chamada,
escopada por `usuario_id` extraído do JWT em `exigir_usuario`.

Categorias sem registro aqui usam a cor padrão do site (resolvida no
frontend) — este módulo só guarda as exceções que o usuário personalizou.
"""

from datetime import datetime, timezone

from agente_oracle.db.connection import get_connection

_tabela_garantida = False


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categoria_cores (
            id BIGSERIAL PRIMARY KEY,
            usuario_id BIGINT NOT NULL,
            categoria VARCHAR NOT NULL,
            cor VARCHAR NOT NULL,
            criado_em TIMESTAMPTZ NOT NULL,
            atualizado_em TIMESTAMPTZ NOT NULL,
            UNIQUE (usuario_id, categoria)
        )
    """)
    _tabela_garantida = True


def listar(usuario_id: int) -> list[dict]:
    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "SELECT categoria, cor FROM categoria_cores WHERE usuario_id = :usuario_id ORDER BY categoria",
            usuario_id=usuario_id,
        )
        linhas = cursor.fetchall()
    return [{"categoria": categoria, "cor": cor} for categoria, cor in linhas]


def definir(usuario_id: int, categoria: str, cor: str) -> dict:
    agora = datetime.now(timezone.utc)

    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "UPDATE categoria_cores SET cor = :cor, atualizado_em = :agora WHERE usuario_id = :usuario_id AND categoria = :categoria",
            usuario_id=usuario_id,
            categoria=categoria,
            cor=cor,
            agora=agora,
        )
        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO categoria_cores (usuario_id, categoria, cor, criado_em, atualizado_em)
                VALUES (:usuario_id, :categoria, :cor, :agora, :agora)
                """,
                usuario_id=usuario_id,
                categoria=categoria,
                cor=cor,
                agora=agora,
            )

    return {"categoria": categoria, "cor": cor}


def remover(usuario_id: int, categoria: str) -> bool:
    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "DELETE FROM categoria_cores WHERE usuario_id = :usuario_id AND categoria = :categoria",
            usuario_id=usuario_id,
            categoria=categoria,
        )
        return cursor.rowcount > 0
