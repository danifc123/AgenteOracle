"""Flags de configuração do módulo TI controláveis pelo próprio time (sem
precisar mexer em `.env`/reiniciar o servidor) — mesmo padrão de tabela
própria auto-criada de `tools/ti/uso_ia_chamados.py`/
`tools/financeiro/categoria_cores.py`.

Formato chave/valor (não uma coluna fixa por flag) pra dar pra guardar uma
segunda configuração de TI no futuro sem precisar de migração nova — cada
linha usa `valor` (flag booleana) OU `valor_numerico` (número), nunca os dois.

Duas configurações hoje:
- `usar_ia_avaliacao_chamado` — desliga a chamada ao Ollama em
  `agent/ti/qualidade_chamado.py::avaliar_chamado` (ver docstring de lá),
  decisão do time de TI, não uma reação automática a falha (isso já existe
  independente desta flag).
- `percentual_amostragem_chamados` — que parcela (0 a 100) dos chamados novos
  a Auditoria analisa; ver `tools/ti/amostragem_chamados.py`. Sem linha
  configurada, o padrão é 100 (todos), ou seja, comportamento de sempre."""

from decimal import Decimal

from agente_oracle.db.connection import get_postgres_connection

_tabela_garantida = False

_CHAVE_PERCENTUAL_AMOSTRAGEM_CHAMADOS = "percentual_amostragem_chamados"
_CHAVE_USAR_IA_AVALIACAO_CHAMADO = "usar_ia_avaliacao_chamado"

PERCENTUAL_AMOSTRAGEM_PADRAO = Decimal(100)


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
    # A tabela já existe em produção só com `valor BOOLEAN NOT NULL` — os dois
    # ALTER abaixo são idempotentes e adaptam ela pra guardar também número.
    cursor.execute("ALTER TABLE ti_configuracoes ADD COLUMN IF NOT EXISTS valor_numerico NUMERIC(6, 3)")
    cursor.execute("ALTER TABLE ti_configuracoes ALTER COLUMN valor DROP NOT NULL")
    _tabela_garantida = True


def usar_ia_avaliacao_chamado() -> bool:
    """Sem linha configurada ainda, o padrão é `True` (IA ligada) — a
    flag é um jeito de desligar, não uma exigência de configurar antes de
    usar."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "SELECT valor FROM ti_configuracoes WHERE chave = :chave", chave=_CHAVE_USAR_IA_AVALIACAO_CHAMADO
        )
        linha = cursor.fetchone()
    return bool(linha[0]) if linha else True


def definir_usar_ia_avaliacao_chamado(valor: bool) -> None:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "UPDATE ti_configuracoes SET valor = :valor WHERE chave = :chave",
            valor=valor,
            chave=_CHAVE_USAR_IA_AVALIACAO_CHAMADO,
        )
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT INTO ti_configuracoes (chave, valor) VALUES (:chave, :valor)",
                chave=_CHAVE_USAR_IA_AVALIACAO_CHAMADO,
                valor=valor,
            )


def definir_percentual_amostragem_chamados(valor: Decimal) -> None:
    """`valor` já validado pela camada de rota (0 a 100, até 3 casas
    decimais) — ver `server/ti/configuracoes.py`."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "UPDATE ti_configuracoes SET valor_numerico = :valor WHERE chave = :chave",
            valor=valor,
            chave=_CHAVE_PERCENTUAL_AMOSTRAGEM_CHAMADOS,
        )
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT INTO ti_configuracoes (chave, valor_numerico) VALUES (:chave, :valor)",
                chave=_CHAVE_PERCENTUAL_AMOSTRAGEM_CHAMADOS,
                valor=valor,
            )


def percentual_amostragem_chamados() -> Decimal:
    """Sem linha configurada ainda, o padrão é 100 (todos os chamados
    novos são analisados) — mesmo espírito de `usar_ia_avaliacao_chamado`: a
    configuração é um jeito de reduzir, não uma exigência antes de usar."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "SELECT valor_numerico FROM ti_configuracoes WHERE chave = :chave",
            chave=_CHAVE_PERCENTUAL_AMOSTRAGEM_CHAMADOS,
        )
        linha = cursor.fetchone()
    return linha[0] if linha and linha[0] is not None else PERCENTUAL_AMOSTRAGEM_PADRAO
