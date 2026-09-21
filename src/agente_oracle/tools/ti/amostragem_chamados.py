"""Amostragem controlada dos chamados que a Auditoria (TI) analisa — em vez de
triar 100% dos chamados novos, analisa só uma parcela (ex: 20%), pra subir a
funcionalidade pra produção aos poucos (`percentual_amostragem_chamados`, em
`tools/ti/configuracoes.py`, editável na tela de Chamados).

Conta acumulada, não sorteio: depois de N chamados novos vistos sob o mesmo
percentual P, exatamente `floor(N × P / 100)` deles entraram na amostra —
10 chamados a 20% dão 2, a 33,333% dão 3 (nunca arredonda pra cima). Uma
conta por lote (a cada rodada do poller) zeraria a amostra com poucos
chamados por vez (20% de 4 = 0,8 → 0), e o webhook manda um chamado só por
chamada; acumulando, o total converge pro percentual mesmo assim. Toda a
conta usa `Decimal` — com `float`, algo como `0,29 × 100` dá 28,999… e o
`floor` perderia um chamado.

Quem entra ou não é decidido UMA vez por chamado e gravado
(`ti_amostragem_chamados`): um chamado fora da amostra continua `novo` no
GLPI, e sem esse registro o poller (a cada 5 min) sortearia ele de novo a
cada rodada, até algum dia cair dentro. Mudar o percentual reinicia a
contagem (só entram na conta as decisões tomadas sob o percentual atual) —
senão subir de 20% pra 50% faria vários chamados seguidos entrarem só pra
"compensar" o histórico.

Só chamado que chega `novo` pela primeira vez passa por aqui: quem já foi
avaliado alguma vez (`uso_ia_chamados`), ou está `aguardando_usuario`,
continua o ciclo normal (resposta nova, escalonamento) — ver
`server/ti/chamados.py`."""

from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal

from agente_oracle.db.connection import get_postgres_connection
from agente_oracle.tools.ti import configuracoes

_tabela_garantida = False

_PERCENTUAL_TODOS = Decimal(100)

# Chave de `pg_advisory_xact_lock` — serializa `deve_analisar` entre o poller
# e o webhook (threads diferentes), senão dois chamados decididos ao mesmo
# tempo leriam a mesma contagem e ambos entrariam (ou ambos ficariam de fora).
_CHAVE_LOCK_DECISAO = 7_301_001


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
    _tabela_garantida = True


def deve_analisar(chamado_id: int) -> bool:
    """Decide (e grava) se o chamado entra na amostra. Chamado já decidido
    antes devolve a mesma resposta de antes, sem recalcular. Com o percentual
    em 100 nem toca a tabela de decisões — o comportamento de sempre, sem
    custo extra."""
    percentual = configuracoes.percentual_amostragem_chamados()
    if percentual >= _PERCENTUAL_TODOS:
        return True

    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("SELECT pg_advisory_xact_lock(:chave)", chave=_CHAVE_LOCK_DECISAO)
        cursor.execute(
            "SELECT amostrado FROM ti_amostragem_chamados WHERE chamado_id = :chamado_id",
            chamado_id=chamado_id,
        )
        decisao_anterior = cursor.fetchone()
        if decisao_anterior is not None:
            return decisao_anterior[0]

        cursor.execute(
            """
            SELECT COUNT(*), COUNT(*) FILTER (WHERE amostrado)
            FROM ti_amostragem_chamados
            WHERE percentual = :percentual
            """,
            percentual=percentual,
        )
        vistos, analisados = cursor.fetchone()
        amostrado = entra_na_amostra(vistos, analisados, percentual)
        cursor.execute(
            """
            INSERT INTO ti_amostragem_chamados (chamado_id, amostrado, percentual, criado_em)
            VALUES (:chamado_id, :amostrado, :percentual, :agora)
            """,
            chamado_id=chamado_id,
            amostrado=amostrado,
            percentual=percentual,
            agora=datetime.now(UTC),
        )
    return amostrado


def entra_na_amostra(vistos_antes: int, analisados_antes: int, percentual: Decimal) -> bool:
    """Regra pura: o próximo chamado entra quando a meta acumulada
    (`floor((vistos_antes + 1) × percentual / 100)`) passa de quantos já
    entraram. `vistos_antes`/`analisados_antes` contam só decisões tomadas
    sob este mesmo `percentual`, sem incluir o chamado atual."""
    meta = ((vistos_antes + 1) * percentual / 100).to_integral_value(rounding=ROUND_FLOOR)
    return meta > analisados_antes


def ids_fora_da_amostra() -> set[int]:
    """Chamados já decididos como "fora da amostra" — a tela de Auditoria
    esconde eles (a IA nunca mexeu, e o time trata como sempre tratou)."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("SELECT chamado_id FROM ti_amostragem_chamados WHERE NOT amostrado")
        return {linha[0] for linha in cursor.fetchall()}
