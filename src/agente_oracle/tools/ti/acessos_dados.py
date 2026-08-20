"""Log de acesso a dado (exportação/download/listagem de registro real) em
todo o sistema — pré-requisito pro agente de detecção de segurança do
módulo TI (`agent/ti/deteccao_seguranca.py`) ter volume de acesso pra
analisar, já que antes disso não existia nenhum registro de quem pegou o
quê. Mesmo padrão de `tools/auth/eventos_seguranca.py`: tabela própria,
criada sozinha (`CREATE TABLE IF NOT EXISTS`), sem migração separada.

`registrar` nunca pode derrubar a exportação de verdade por causa de uma
falha ao logar — mesmo espírito de `eventos_seguranca.registrar` (captura
`DatabaseError` e segue em frente)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from agente_oracle.db.connection import DatabaseError, get_postgres_connection

_tabela_garantida = False


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ti_acessos_dados (
            id BIGSERIAL PRIMARY KEY,
            usuario_id VARCHAR NOT NULL,
            modulo VARCHAR NOT NULL,
            recurso VARCHAR NOT NULL,
            quantidade_registros INTEGER NOT NULL,
            criado_em TIMESTAMPTZ NOT NULL
        )
    """)
    _tabela_garantida = True


@dataclass(frozen=True)
class PerfilAcesso:
    usuario_id: str
    modulo: str
    recurso: str
    total_registros: int
    ocorrencias: int


def perfil_acessos(dias: int) -> list[PerfilAcesso]:
    """Acesso a dado agregado por `(usuario, módulo, recurso)` nos últimos
    `dias` dias — é isso (nunca a linha crua) que alimenta o agente de
    detecção, mesmo princípio de `agent/auditoria/perfil_campo.py`."""
    desde = datetime.now(UTC) - timedelta(days=dias)

    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            SELECT usuario_id, modulo, recurso, SUM(quantidade_registros) AS total, COUNT(*) AS ocorrencias
            FROM ti_acessos_dados
            WHERE criado_em >= :desde
            GROUP BY usuario_id, modulo, recurso
            ORDER BY total DESC
            """,
            desde=desde,
        )
        linhas = cursor.fetchall()

    return [
        PerfilAcesso(
            usuario_id=usuario_id,
            modulo=modulo,
            recurso=recurso,
            total_registros=int(total),
            ocorrencias=int(ocorrencias),
        )
        for usuario_id, modulo, recurso, total, ocorrencias in linhas
    ]


def registrar(usuario_id: str, modulo: str, recurso: str, quantidade_registros: int) -> None:
    try:
        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute(
                """
                INSERT INTO ti_acessos_dados (usuario_id, modulo, recurso, quantidade_registros, criado_em)
                VALUES (:usuario_id, :modulo, :recurso, :quantidade_registros, :criado_em)
                """,
                usuario_id=usuario_id,
                modulo=modulo,
                recurso=recurso,
                quantidade_registros=quantidade_registros,
                criado_em=datetime.now(UTC),
            )
    except DatabaseError:
        pass
