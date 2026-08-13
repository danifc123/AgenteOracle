"""Bloqueio de filial por usuário — cada coordenador (papel administrador de
um módulo, ex: `financeiro_admin`) decide quais filiais um usuário do seu
departamento NÃO pode ver, dentre as que aparecem nos relatórios desse
módulo. Modelo é "lista de bloqueio": por padrão todo usuário vê todas as
filiais; só as marcadas aqui ficam de fora.

Desenhado por `modulo` (não fixo em "financeiro") porque outro módulo
(Estoque, quando ganhar filial de verdade no backend) reaproveita a mesma
tabela sem precisar de nada novo — só chamar com `modulo="estoque"`. Hoje
só o Financeiro de fato aplica a checagem (`server/financeiro/relatorios/
_comum.py::exigir_filiais_liberadas`).

Mesmo padrão de `tools/auth/usuarios.py`/`tools/auth/eventos_seguranca.py`:
tabela própria, criada sozinha (`CREATE TABLE IF NOT EXISTS`), sem migração
separada."""

from datetime import UTC, datetime

from agente_oracle.db.connection import get_postgres_connection

_tabela_garantida = False


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS filiais_bloqueadas (
            id BIGSERIAL PRIMARY KEY,
            usuario_id BIGINT NOT NULL,
            modulo VARCHAR NOT NULL,
            filial VARCHAR NOT NULL,
            criado_em TIMESTAMPTZ NOT NULL,
            UNIQUE (usuario_id, modulo, filial)
        )
    """)
    _tabela_garantida = True


def definir_bloqueadas(usuario_id: int, modulo: str, filiais: list[str]) -> list[str]:
    """Substitui TODAS as filiais bloqueadas desse usuário nesse módulo pela
    lista informada (lista vazia = desbloqueia tudo) — semântica de "salvar
    a seleção inteira", que é como a tela de administração usa (um
    multi-select, não bloquear/desbloquear uma de cada vez). Devolve a lista
    já normalizada (sem duplicata, ordenada) que ficou salva."""
    filiais_normalizadas = sorted({filial.strip() for filial in filiais if filial.strip()})
    agora = datetime.now(UTC)

    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "DELETE FROM filiais_bloqueadas WHERE usuario_id = :usuario_id AND modulo = :modulo",
            usuario_id=usuario_id,
            modulo=modulo,
        )
        for filial in filiais_normalizadas:
            cursor.execute(
                """
                INSERT INTO filiais_bloqueadas (usuario_id, modulo, filial, criado_em)
                VALUES (:usuario_id, :modulo, :filial, :criado_em)
                """,
                usuario_id=usuario_id,
                modulo=modulo,
                filial=filial,
                criado_em=agora,
            )

    return filiais_normalizadas


def filiais_bloqueadas(usuario_id: int, modulo: str) -> set[str]:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "SELECT filial FROM filiais_bloqueadas WHERE usuario_id = :usuario_id AND modulo = :modulo",
            usuario_id=usuario_id,
            modulo=modulo,
        )
        linhas = cursor.fetchall()

    return {linha[0] for linha in linhas}


def remover_usuario(usuario_id: int) -> None:
    """Limpa todo bloqueio de filial (de qualquer módulo) de um usuário —
    chamada por `tools/auth/usuarios.py::deletar_usuario` antes de apagar o
    usuário, pra não deixar linha órfã na tabela."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("DELETE FROM filiais_bloqueadas WHERE usuario_id = :usuario_id", usuario_id=usuario_id)
