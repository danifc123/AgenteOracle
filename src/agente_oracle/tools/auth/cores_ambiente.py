"""Cores de ambiente personalizadas (barra lateral, destaque etc.) por
usuário — igual `tools/financeiro/categoria_cores.py`: tabela própria,
criada sozinha (`CREATE TABLE IF NOT EXISTS`) na primeira chamada, escopada
por `usuario_id` extraído do JWT em `exigir_usuario`. Diferente daquele
módulo, mora em `tools/auth/` (não `tools/financeiro/`) porque é
autoatendimento aberto a QUALQUER usuário autenticado, não travado a um
módulo — mesmo espírito de `tools/auth/layout_dashboard.py`.

`token` é o nome da variável CSS (ex: "--color-primary") — a lista de quais
tokens são editáveis é decidida por quem chama (`server/auth/cores_ambiente.py`),
não aqui: esta camada só guarda pares (token, cor) por usuário, sem saber o
que cada um significa visualmente."""

from datetime import UTC, datetime

from agente_oracle.db.connection import get_postgres_connection

_tabela_garantida = False


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cores_ambiente (
            id BIGSERIAL PRIMARY KEY,
            usuario_id BIGINT NOT NULL,
            token VARCHAR NOT NULL,
            cor VARCHAR NOT NULL,
            criado_em TIMESTAMPTZ NOT NULL,
            atualizado_em TIMESTAMPTZ NOT NULL,
            UNIQUE (usuario_id, token)
        )
    """)
    _tabela_garantida = True


def definir(usuario_id: int, token: str, cor: str) -> dict:
    agora = datetime.now(UTC)

    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "UPDATE cores_ambiente SET cor = :cor, atualizado_em = :agora WHERE usuario_id = :usuario_id AND token = :token",
            usuario_id=usuario_id,
            token=token,
            cor=cor,
            agora=agora,
        )
        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO cores_ambiente (usuario_id, token, cor, criado_em, atualizado_em)
                VALUES (:usuario_id, :token, :cor, :agora, :agora)
                """,
                usuario_id=usuario_id,
                token=token,
                cor=cor,
                agora=agora,
            )

    return {"token": token, "cor": cor}


def listar(usuario_id: int) -> list[dict]:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "SELECT token, cor FROM cores_ambiente WHERE usuario_id = :usuario_id ORDER BY token",
            usuario_id=usuario_id,
        )
        linhas = cursor.fetchall()
    return [{"token": token, "cor": cor} for token, cor in linhas]


def remover(usuario_id: int, token: str) -> bool:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "DELETE FROM cores_ambiente WHERE usuario_id = :usuario_id AND token = :token",
            usuario_id=usuario_id,
            token=token,
        )
        return cursor.rowcount > 0


def remover_usuario(usuario_id: int) -> None:
    """Limpa as cores personalizadas de um usuário — chamada por
    `tools/auth/usuarios.py::deletar_usuario` antes de apagar o usuário,
    pra não deixar linha órfã na tabela (mesmo padrão de
    `restricoes_filial.remover_usuario`/`layout_dashboard.remover_usuario`)."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("DELETE FROM cores_ambiente WHERE usuario_id = :usuario_id", usuario_id=usuario_id)
