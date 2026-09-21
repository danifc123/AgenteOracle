"""Acesso a dados da amostragem de chamados (`ti_amostragem_chamados`)."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from agente_oracle.db.connection import get_postgres_connection
from agente_oracle.tools.ti import uso_ia_chamados

_tabela_garantida = False

# Serializa decisões concorrentes (poller e webhook rodam em threads diferentes).
_CHAVE_LOCK_DECISAO = 7_301_001

_CONTAGEM_HISTORICO = """
    SELECT COUNT(*), COUNT(*) FILTER (WHERE amostrado)
    FROM ti_amostragem_chamados
    WHERE conta_na_cota
"""

_CONTAGEM_REGIME = """
    SELECT COUNT(*), COUNT(*) FILTER (WHERE amostrado)
    FROM ti_amostragem_chamados
    WHERE conta_na_cota
      AND percentual = :percentual
      AND regime_desde IS NOT DISTINCT FROM CAST(:regime AS TIMESTAMPTZ)
"""


@dataclass(frozen=True)
class Decisao:
    """`conta_na_cota` é falso pro chamado antigo ignorado; `regime_desde` é a
    data de referência em vigor quando a decisão foi tomada."""

    amostrado: bool
    conta_na_cota: bool
    regime_desde: datetime | None


class Transacao:
    """Operações de uma decisão, todas na mesma conexão e sob o lock."""

    def __init__(self, cursor) -> None:
        self._cursor = cursor

    def buscar(self, chamado_id: int) -> Decisao | None:
        self._cursor.execute(
            "SELECT amostrado, conta_na_cota, regime_desde FROM ti_amostragem_chamados WHERE chamado_id = :id",
            id=chamado_id,
        )
        linha = self._cursor.fetchone()
        return Decisao(*linha) if linha else None

    def contar(
        self, percentual: Decimal, regime: datetime | None, historico_inteiro: bool
    ) -> tuple[int, int]:
        """(chamados contados, quantos foram analisados); só o regime atual, ou tudo."""
        if historico_inteiro:
            self._cursor.execute(_CONTAGEM_HISTORICO)
        else:
            self._cursor.execute(_CONTAGEM_REGIME, percentual=percentual, regime=regime)
        contados, analisados = self._cursor.fetchone()
        return contados, analisados

    def gravar(self, chamado_id: int, decisao: Decisao, percentual: Decimal, ja_existe: bool) -> None:
        if ja_existe:
            self._atualizar(chamado_id, decisao, percentual)
        else:
            self._inserir(chamado_id, decisao, percentual)

    def _atualizar(self, chamado_id: int, decisao: Decisao, percentual: Decimal) -> None:
        self._cursor.execute(
            """
            UPDATE ti_amostragem_chamados
            SET amostrado = :amostrado, percentual = :percentual,
                regime_desde = :regime, conta_na_cota = :conta
            WHERE chamado_id = :id
            """,
            **_binds(chamado_id, decisao, percentual),
        )

    def _inserir(self, chamado_id: int, decisao: Decisao, percentual: Decimal) -> None:
        self._cursor.execute(
            """
            INSERT INTO ti_amostragem_chamados
                (chamado_id, amostrado, percentual, criado_em, regime_desde, conta_na_cota)
            VALUES (:id, :amostrado, :percentual, :agora, :regime, :conta)
            """,
            agora=datetime.now(UTC),
            **_binds(chamado_id, decisao, percentual),
        )


def _binds(chamado_id: int, decisao: Decisao, percentual: Decimal) -> dict:
    return {
        "id": chamado_id,
        "amostrado": decisao.amostrado,
        "percentual": percentual,
        "regime": decisao.regime_desde,
        "conta": decisao.conta_na_cota,
    }


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ti_amostragem_chamados (
            chamado_id BIGINT PRIMARY KEY,
            amostrado BOOLEAN NOT NULL,
            percentual NUMERIC(6, 3) NOT NULL,
            criado_em TIMESTAMPTZ NOT NULL
        )
    """)
    cursor.execute("ALTER TABLE ti_amostragem_chamados ADD COLUMN IF NOT EXISTS regime_desde TIMESTAMPTZ")
    cursor.execute(
        "ALTER TABLE ti_amostragem_chamados ADD COLUMN IF NOT EXISTS conta_na_cota BOOLEAN NOT NULL DEFAULT TRUE"
    )
    _tabela_garantida = True


def ids_fora_da_amostra() -> set[int]:
    """Chamados fora da amostra que ainda não foram avaliados."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        uso_ia_chamados.garantir_tabela(cursor)
        cursor.execute("""
            SELECT a.chamado_id
            FROM ti_amostragem_chamados a
            WHERE NOT a.amostrado
              AND NOT EXISTS (SELECT 1 FROM ti_uso_ia_chamados u WHERE u.chamado_id = a.chamado_id)
        """)
        return {linha[0] for linha in cursor.fetchall()}


@contextmanager
def transacao() -> Iterator[Transacao]:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("SELECT pg_advisory_xact_lock(:chave)", chave=_CHAVE_LOCK_DECISAO)
        yield Transacao(cursor)
