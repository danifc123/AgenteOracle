"""Cache de clima regional por município — evita geocodificar/consultar a
Open-Meteo de novo pro mesmo município a cada request do Score de
Inadimplência (muitos clientes dividem o mesmo município). Mesmo padrão
de `tools/financeiro/categoria_cores.py`: tabela própria no Postgres
(estado do sistema — ver `db/connection.py`), criada sozinha (`CREATE
TABLE IF NOT EXISTS`), sem migração separada."""

from datetime import UTC, datetime, timedelta

from agente_oracle.agent.financeiro.clima_regional import IndicadorClima
from agente_oracle.db.connection import get_postgres_connection

TEMPO_EXPIRACAO = timedelta(hours=24)

_tabela_garantida = False


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS financeiro_clima_municipio (
            id BIGSERIAL PRIMARY KEY,
            municipio_nome VARCHAR NOT NULL,
            uf VARCHAR NOT NULL,
            anomalia_precipitacao_percentual DOUBLE PRECISION,
            classificacao VARCHAR NOT NULL,
            calculado_em TIMESTAMPTZ NOT NULL,
            UNIQUE (municipio_nome, uf)
        )
    """)
    _tabela_garantida = True


def buscar_cache(municipio_nome: str, uf: str) -> IndicadorClima | None:
    """Devolve o indicador salvo pra esse município se ainda não passou de
    `TEMPO_EXPIRACAO`, ou None se não houver cache ou estiver velho (quem
    chama recalcula e chama `salvar_cache` nesse caso)."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            SELECT anomalia_precipitacao_percentual, classificacao, calculado_em
            FROM financeiro_clima_municipio
            WHERE municipio_nome = :municipio_nome AND uf = :uf
            """,
            municipio_nome=municipio_nome,
            uf=uf,
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


def salvar_cache(indicador: IndicadorClima) -> None:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            INSERT INTO financeiro_clima_municipio
                (municipio_nome, uf, anomalia_precipitacao_percentual, classificacao, calculado_em)
            VALUES (:municipio_nome, :uf, :anomalia, :classificacao, :agora)
            ON CONFLICT (municipio_nome, uf) DO UPDATE SET
                anomalia_precipitacao_percentual = EXCLUDED.anomalia_precipitacao_percentual,
                classificacao = EXCLUDED.classificacao,
                calculado_em = EXCLUDED.calculado_em
            """,
            municipio_nome=indicador.municipio_nome,
            uf=indicador.uf,
            anomalia=indicador.anomalia_precipitacao_percentual,
            classificacao=indicador.classificacao,
            agora=datetime.now(UTC),
        )
