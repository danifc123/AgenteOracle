"""Log de uso de IA na triagem de chamados (TI) — cada vez que um chamado
novo é processado (`server/ti/chamados.py::processar_chamado_novo`, tanto
via `/api/ti/chamados/verificar` quanto via `server/ti/webhook_glpi.py`),
grava aqui quantas chamadas de IA aquilo custou e quanto tempo levou.

Existe pra responder "isso não tá saindo caro?" com número real em vez de
estimativa — com Ollama local (`OLLAMA_HOST=127.0.0.1`, ver `config.py`),
não tem custo em dinheiro por chamada, então o que importa medir é volume
e tempo de processamento (carga na máquina), não uma fatura. `precisou_embedding`
é o proxy de "chamado caro" (regra por palavra-chave não resolveu a área,
precisou do fallback via `agent/ti/roteamento_chamado.py`) — se a maioria
dos chamados precisar do fallback, vale revisar a lista de palavras-chave
antes de qualquer outra coisa.

Mesmo padrão de `tools/ti/acessos_dados.py`: tabela própria, criada
sozinha (`CREATE TABLE IF NOT EXISTS`), e `registrar` nunca pode derrubar
o processamento real do chamado por causa de falha ao logar.

De propósito, só é chamado pela camada de rota (`chamados_verificar_route`/
`glpi_webhook_route`), nunca por `processar_chamado_novo`/`processar_webhook`
em si — assim os dois continuam testáveis com fake `ClienteGLPI`/Ollama,
sem precisar de Postgres real só pra rodar teste unitário."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from agente_oracle.db.connection import DatabaseError, get_postgres_connection

_tabela_garantida = False


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ti_uso_ia_chamados (
            id BIGSERIAL PRIMARY KEY,
            chamado_id BIGINT NOT NULL,
            avaliacao_suficiente BOOLEAN NOT NULL,
            precisou_embedding BOOLEAN,
            duracao_ms INTEGER NOT NULL,
            criado_em TIMESTAMPTZ NOT NULL
        )
    """)
    _tabela_garantida = True


@dataclass(frozen=True)
class ResumoUsoIa:
    total_chamados: int
    total_avaliados_insuficientes: int
    total_com_fallback_embedding: int
    duracao_total_ms: int
    duracao_media_ms: float


def registrar(
    chamado_id: int, avaliacao_suficiente: bool, precisou_embedding: bool | None, duracao_ms: int
) -> None:
    """`precisou_embedding` é `None` quando a avaliação já deu insuficiente
    — o chamado nem chegou a `classificar_categoria`, então a pergunta
    "precisou de embedding" não se aplica (não é `False`, que significaria
    `usar_ia=False`, ou seja, a etapa rodou mas sem chamar o Ollama)."""
    try:
        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute(
                """
                INSERT INTO ti_uso_ia_chamados
                    (chamado_id, avaliacao_suficiente, precisou_embedding, duracao_ms, criado_em)
                VALUES (:chamado_id, :avaliacao_suficiente, :precisou_embedding, :duracao_ms, :agora)
                """,
                chamado_id=chamado_id,
                avaliacao_suficiente=avaliacao_suficiente,
                precisou_embedding=precisou_embedding,
                duracao_ms=duracao_ms,
                agora=datetime.now(UTC),
            )
    except DatabaseError:
        pass


def resumo_uso(dias: int) -> ResumoUsoIa:
    """Agregado dos últimos `dias` dias — o número real pra decidir se a
    IA nessa etapa está saindo cara (tempo de processamento) ou não, em
    vez de estimar no escuro. Nada aqui envolve dinheiro por chamada
    (Ollama local); é volume e duração, que são os dois fatores que
    importam pra carga de máquina."""
    desde = datetime.now(UTC) - timedelta(days=dias)
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            SELECT
                COUNT(*),
                COUNT(*) FILTER (WHERE NOT avaliacao_suficiente),
                COUNT(*) FILTER (WHERE precisou_embedding),
                COALESCE(SUM(duracao_ms), 0),
                COALESCE(AVG(duracao_ms), 0)
            FROM ti_uso_ia_chamados
            WHERE criado_em >= :desde
            """,
            desde=desde,
        )
        total, insuficientes, com_embedding, duracao_total, duracao_media = cursor.fetchone()
    return ResumoUsoIa(
        total_chamados=total,
        total_avaliados_insuficientes=insuficientes,
        total_com_fallback_embedding=com_embedding,
        duracao_total_ms=int(duracao_total),
        duracao_media_ms=float(duracao_media),
    )
