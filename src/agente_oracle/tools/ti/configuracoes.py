"""Configurações do módulo TI editáveis sem reiniciar o servidor (`ti_configuracoes`).

Cada linha guarda `valor` (flag), `valor_numerico` (número) e/ou `valor_data` (quando mudou).
"""

from datetime import UTC, datetime
from decimal import Decimal

from agente_oracle.db.connection import get_postgres_connection

_tabela_garantida = False

_CHAVE_LER_CHAMADOS_ANTIGOS = "ler_chamados_antigos"
_CHAVE_PERCENTUAL_AMOSTRAGEM_CHAMADOS = "percentual_amostragem_chamados"
_CHAVE_USAR_IA_AVALIACAO_CHAMADO = "usar_ia_avaliacao_chamado"

PERCENTUAL_AMOSTRAGEM_PADRAO = Decimal(100)


def _buscar_percentual(cursor) -> tuple | None:
    cursor.execute(
        "SELECT valor_numerico, valor_data FROM ti_configuracoes WHERE chave = :chave",
        chave=_CHAVE_PERCENTUAL_AMOSTRAGEM_CHAMADOS,
    )
    return cursor.fetchone()


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ti_configuracoes (
            chave VARCHAR PRIMARY KEY,
            valor BOOLEAN NOT NULL
        )
    """)
    cursor.execute("ALTER TABLE ti_configuracoes ADD COLUMN IF NOT EXISTS valor_numerico NUMERIC(6, 3)")
    cursor.execute("ALTER TABLE ti_configuracoes ADD COLUMN IF NOT EXISTS valor_data TIMESTAMPTZ")
    cursor.execute("ALTER TABLE ti_configuracoes ALTER COLUMN valor DROP NOT NULL")
    _tabela_garantida = True


def _gravar_booleano(chave: str, valor: bool) -> None:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "UPDATE ti_configuracoes SET valor = :valor WHERE chave = :chave", valor=valor, chave=chave
        )
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT INTO ti_configuracoes (chave, valor) VALUES (:chave, :valor)",
                chave=chave,
                valor=valor,
            )


def _ler_booleano(chave: str, padrao: bool) -> bool:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("SELECT valor FROM ti_configuracoes WHERE chave = :chave", chave=chave)
        linha = cursor.fetchone()
    return bool(linha[0]) if linha and linha[0] is not None else padrao


def definir_ler_chamados_antigos(valor: bool) -> None:
    _gravar_booleano(_CHAVE_LER_CHAMADOS_ANTIGOS, valor)


def definir_percentual_amostragem_chamados(valor: Decimal) -> None:
    """Só uma mudança de verdade move a data de referência; regravar o mesmo valor não."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        linha = _buscar_percentual(cursor)
        em_vigor = linha[0] if linha and linha[0] is not None else PERCENTUAL_AMOSTRAGEM_PADRAO
        alterado_em = datetime.now(UTC) if valor != em_vigor else None
        _gravar_percentual(cursor, valor, alterado_em, existe=linha is not None)


def _gravar_percentual(cursor, valor: Decimal, alterado_em: datetime | None, existe: bool) -> None:
    """Insere a linha se não existe; atualiza só quando o percentual mudou de verdade."""
    if not existe:
        cursor.execute(
            "INSERT INTO ti_configuracoes (chave, valor_numerico, valor_data) VALUES (:chave, :valor, :quando)",
            chave=_CHAVE_PERCENTUAL_AMOSTRAGEM_CHAMADOS,
            valor=valor,
            quando=alterado_em,
        )
    elif alterado_em is not None:
        cursor.execute(
            "UPDATE ti_configuracoes SET valor_numerico = :valor, valor_data = :quando WHERE chave = :chave",
            chave=_CHAVE_PERCENTUAL_AMOSTRAGEM_CHAMADOS,
            valor=valor,
            quando=alterado_em,
        )


def definir_usar_ia_avaliacao_chamado(valor: bool) -> None:
    _gravar_booleano(_CHAVE_USAR_IA_AVALIACAO_CHAMADO, valor)


def ler_chamados_antigos() -> bool:
    return _ler_booleano(_CHAVE_LER_CHAMADOS_ANTIGOS, padrao=False)


def percentual_alterado_em() -> datetime | None:
    """Quando o percentual mudou pela última vez; `None` se nunca (nenhum chamado é antigo)."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        linha = _buscar_percentual(cursor)
    return linha[1] if linha else None


def percentual_amostragem_chamados() -> Decimal:
    """Padrão 100 (todos os chamados novos são analisados)."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        linha = _buscar_percentual(cursor)
    return linha[0] if linha and linha[0] is not None else PERCENTUAL_AMOSTRAGEM_PADRAO


def usar_ia_avaliacao_chamado() -> bool:
    return _ler_booleano(_CHAVE_USAR_IA_AVALIACAO_CHAMADO, padrao=True)
