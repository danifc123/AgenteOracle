"""Cache de clima regional por (município, janela) — evita geocodificar/
consultar a Open-Meteo de novo pra mesma janela de safra num mesmo
município (muitos clientes dividem o mesmo município, e podem até
compartilhar a mesma janela quando estão na mesma safra). Mesmo padrão de
`tools/financeiro/categoria_cores.py`: tabela própria no Postgres (estado
do sistema — ver `db/connection.py`), criada sozinha (`CREATE TABLE IF NOT
EXISTS`), sem migração separada.

Tabela `financeiro_clima_safra` (não `financeiro_clima_municipio`, o nome
antigo): a janela consultada mudou de fixa (últimos 30 dias) pra ser a
janela real de cada safra (ver `agent/financeiro/clima_regional.py`), então
a chave de cache precisou ganhar `inicio`/`fim` — como é só cache (TTL de
24h, sem dado que precise ser preservado), a forma mais simples de mudar o
formato sem migração foi nascer numa tabela nova; a antiga fica órfã, sem
problema."""

from datetime import UTC, date, datetime, timedelta

from agente_oracle.agent.financeiro.clima_regional import IndicadorClima
from agente_oracle.db.connection import get_postgres_connection

TEMPO_EXPIRACAO = timedelta(hours=24)

_tabela_garantida = False


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS financeiro_clima_safra (
            id BIGSERIAL PRIMARY KEY,
            municipio_nome VARCHAR NOT NULL,
            uf VARCHAR NOT NULL,
            inicio DATE NOT NULL,
            fim DATE NOT NULL,
            anomalia_precipitacao_percentual DOUBLE PRECISION,
            classificacao VARCHAR NOT NULL,
            calculado_em TIMESTAMPTZ NOT NULL,
            UNIQUE (municipio_nome, uf, inicio, fim)
        )
    """)
    _tabela_garantida = True


def buscar_cache(municipio_nome: str, uf: str, inicio: date, fim: date) -> IndicadorClima | None:
    """Devolve o indicador salvo pra esse município+janela se ainda não
    passou de `TEMPO_EXPIRACAO`, ou None se não houver cache ou estiver
    velho (quem chama recalcula e chama `salvar_cache` nesse caso)."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            SELECT anomalia_precipitacao_percentual, classificacao, calculado_em
            FROM financeiro_clima_safra
            WHERE municipio_nome = :municipio_nome AND uf = :uf AND inicio = :inicio AND fim = :fim
            """,
            municipio_nome=municipio_nome,
            uf=uf,
            inicio=inicio,
            fim=fim,
        )
        linha = cursor.fetchone()

    if linha is None:
        return None

    anomalia, classificacao, calculado_em = linha
    if datetime.now(UTC) - calculado_em > TEMPO_EXPIRACAO:
        return None

    return IndicadorClima(
        municipio_nome=municipio_nome,
        uf=uf,
        anomalia_precipitacao_percentual=anomalia,
        classificacao=classificacao,
    )


def salvar_cache(indicador: IndicadorClima, inicio: date, fim: date) -> None:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            INSERT INTO financeiro_clima_safra
                (municipio_nome, uf, inicio, fim, anomalia_precipitacao_percentual, classificacao, calculado_em)
            VALUES (:municipio_nome, :uf, :inicio, :fim, :anomalia, :classificacao, :agora)
            ON CONFLICT (municipio_nome, uf, inicio, fim) DO UPDATE SET
                anomalia_precipitacao_percentual = EXCLUDED.anomalia_precipitacao_percentual,
                classificacao = EXCLUDED.classificacao,
                calculado_em = EXCLUDED.calculado_em
            """,
            municipio_nome=indicador.municipio_nome,
            uf=indicador.uf,
            inicio=inicio,
            fim=fim,
            anomalia=indicador.anomalia_precipitacao_percentual,
            classificacao=indicador.classificacao,
            agora=datetime.now(UTC),
        )
