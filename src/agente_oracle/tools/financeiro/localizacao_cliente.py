"""Cadastro manual de localização do cliente pro Score de Inadimplência
(`server/financeiro/score_inadimplencia.py`) — quando o cliente cadastrado
aqui, o clima usa a localização informada em vez do centro do município
(ver `agent/financeiro/clima_regional.py::buscar_indicador_clima_por_coordenadas`).
Mesmo padrão de `tools/financeiro/categoria_cores.py`: tabela própria no
Postgres, criada sozinha (`CREATE TABLE IF NOT EXISTS`).

Campos estruturados (cidade, bairro, coordenadas) em vez de texto livre —
achado desta sessão testando com o usuário: a Open-Meteo trata `"bairro,
cidade"` como um nome literal só (não separa os dois pra tentar cada um),
então bairro pequeno praticamente nunca é encontrado. Com os campos já
vindo separados do formulário, dá pra tentar bairro+cidade e cair pra só
cidade sem precisar adivinhar onde um termina e o outro começa.

A resolução (coordenada direta ou geocodificação) acontece na hora de
`salvar`, não a cada cálculo de score — cliente cadastrado fica rápido (lê
lat/long pronta) e nunca depende da Open-Meteo estar respondendo bem no
instante do score."""

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from agente_oracle.agent.financeiro.clima_regional import _geocodificar
from agente_oracle.db.connection import get_postgres_connection

_tabela_garantida = False


@dataclass(frozen=True)
class LocalizacaoCliente:
    cliente_codigo: str
    cidade: str | None
    bairro: str | None
    latitude: float | None
    longitude: float | None
    resolvido: bool


def _texto_busca(cidade: str | None, bairro: str | None) -> str | None:
    """Monta o texto pra geocodificar a partir dos campos separados —
    `bairro` só entra se `cidade` também tiver sido informada (bairro
    sozinho, sem cidade, é ambíguo demais pra geocodificação)."""
    if not cidade:
        return None
    return f"{bairro}, {cidade}" if bairro else cidade


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS financeiro_localizacao_cliente (
            id BIGSERIAL PRIMARY KEY,
            cliente_codigo VARCHAR NOT NULL UNIQUE,
            cidade VARCHAR,
            bairro VARCHAR,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            resolvido BOOLEAN NOT NULL,
            atualizado_em TIMESTAMPTZ NOT NULL
        )
    """)
    _tabela_garantida = True


def buscar(cliente_codigo: str) -> LocalizacaoCliente | None:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            SELECT cidade, bairro, latitude, longitude, resolvido
            FROM financeiro_localizacao_cliente
            WHERE cliente_codigo = :cliente_codigo
            """,
            cliente_codigo=cliente_codigo,
        )
        linha = cursor.fetchone()

    if linha is None:
        return None
    cidade, bairro, latitude, longitude, resolvido = linha
    return LocalizacaoCliente(cliente_codigo, cidade, bairro, latitude, longitude, resolvido)


def buscar_varios(clientes_codigos: list[str]) -> dict[str, LocalizacaoCliente]:
    """Mesmo padrão de `_buscar_municipios` em `server/financeiro/
    score_inadimplencia.py` — cliente sem cadastro não entra no dict."""
    if not clientes_codigos:
        return {}
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            SELECT cliente_codigo, cidade, bairro, latitude, longitude, resolvido
            FROM financeiro_localizacao_cliente
            WHERE cliente_codigo = ANY(:clientes_codigos)
            """,
            clientes_codigos=clientes_codigos,
        )
        linhas = cursor.fetchall()
    return {
        cliente_codigo: LocalizacaoCliente(cliente_codigo, cidade, bairro, latitude, longitude, resolvido)
        for cliente_codigo, cidade, bairro, latitude, longitude, resolvido in linhas
    }


async def salvar(
    http_client: httpx.AsyncClient,
    cliente_codigo: str,
    cidade: str | None,
    bairro: str | None,
    latitude: float | None,
    longitude: float | None,
) -> LocalizacaoCliente:
    """Coordenada informada (as duas) tem prioridade — usa direto, sem
    geocodificar. Senão, geocodifica `bairro + cidade`; não encontrando (e
    só se `bairro` foi informado), tenta de novo só com `cidade` — bairro
    pequeno geralmente não existe na base da Open-Meteo (GeoNames), mas a
    cidade sozinha costuma existir. Não resolvendo de jeito nenhum, salva
    mesmo assim com `resolvido = False` (quem chamou decide o que avisar;
    o score cai no fallback de município nesse caso)."""
    coordenadas = (latitude, longitude) if latitude is not None and longitude is not None else None

    if coordenadas is None:
        texto_busca = _texto_busca(cidade, bairro)
        if texto_busca is not None:
            coordenadas = await _geocodificar(http_client, texto_busca)
        if coordenadas is None and bairro and cidade:
            coordenadas = await _geocodificar(http_client, cidade)

    latitude_resolvida, longitude_resolvida = coordenadas if coordenadas is not None else (None, None)
    resolvido = coordenadas is not None

    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            INSERT INTO financeiro_localizacao_cliente
                (cliente_codigo, cidade, bairro, latitude, longitude, resolvido, atualizado_em)
            VALUES (:cliente_codigo, :cidade, :bairro, :latitude, :longitude, :resolvido, :agora)
            ON CONFLICT (cliente_codigo) DO UPDATE SET
                cidade = EXCLUDED.cidade,
                bairro = EXCLUDED.bairro,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                resolvido = EXCLUDED.resolvido,
                atualizado_em = EXCLUDED.atualizado_em
            """,
            cliente_codigo=cliente_codigo,
            cidade=cidade,
            bairro=bairro,
            latitude=latitude_resolvida,
            longitude=longitude_resolvida,
            resolvido=resolvido,
            agora=datetime.now(UTC),
        )

    return LocalizacaoCliente(
        cliente_codigo, cidade, bairro, latitude_resolvida, longitude_resolvida, resolvido
    )
