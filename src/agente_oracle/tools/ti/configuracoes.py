"""Flags de configuração do módulo TI controláveis pelo próprio time (sem
precisar mexer em `.env`/reiniciar o servidor) — mesmo padrão de tabela
própria auto-criada de `tools/ti/uso_ia_chamados.py`/
`tools/financeiro/categoria_cores.py`.

Formato chave/valor (não uma coluna fixa por flag) pra dar pra guardar uma
segunda configuração de TI no futuro sem precisar de migração nova.

Hoje só existe `usar_ia_avaliacao_chamado` — desliga a chamada ao Ollama em
`agent/ti/qualidade_chamado.py::avaliar_chamado` (ver docstring de lá),
decisão do time de TI, não uma reação automática a falha (isso já existe
independente desta flag)."""

from agente_oracle.db.connection import get_postgres_connection

_tabela_garantida = False

_CHAVE_USAR_IA_AVALIACAO_CHAMADO = "usar_ia_avaliacao_chamado"


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
