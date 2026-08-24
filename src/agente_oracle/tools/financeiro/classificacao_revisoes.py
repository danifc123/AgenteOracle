"""Revisão (aceitar/corrigir) de sugestão de Classificação Contábil — mesmo
padrão de `tools/auditoria/dispensados.py`: a sugestão em si não tem id
próprio (é sempre recalculada do zero em `agent/financeiro/
classificacao_contabil.py`), então o registro fica guardado no nosso
Postgres, identificado pela chave natural do lançamento
(`documento`+`linha`, mesma usada pelo `track` do frontend). Nunca escreve
no Oracle/STAGE — a "conta certa" aqui é só pra medir precisão, não uma
correção de verdade no plano de contas real.

Sem essa revisão, o "99% de precisão" da planilha de demandas não passa de
uma esperança — `resumo_precisao()` é o número medido de verdade, a partir
do que o time realmente confirma/corrige."""

from datetime import UTC, datetime

from agente_oracle.db.connection import get_postgres_connection

_RESULTADOS_VALIDOS = {"aceita", "corrigida"}

_tabela_garantida = False


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS classificacao_contabil_revisoes (
            id BIGSERIAL PRIMARY KEY,
            modulo VARCHAR NOT NULL DEFAULT 'financeiro',
            usuario VARCHAR NOT NULL,
            documento VARCHAR NOT NULL,
            linha VARCHAR NOT NULL,
            conta_sugerida VARCHAR NOT NULL,
            resultado VARCHAR NOT NULL,
            conta_correta VARCHAR,
            revisado_em TIMESTAMPTZ NOT NULL,
            UNIQUE (documento, linha)
        )
    """)
    _tabela_garantida = True


def chaves_revisadas() -> set[tuple[str, str]]:
    """Todo `(documento, linha)` já revisado (aceito ou corrigido) — usado
    pra tirar da fila de sugestão um lançamento que o time já resolveu,
    já que a rota recalcula tudo do zero a cada chamada."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("SELECT documento, linha FROM classificacao_contabil_revisoes")
        linhas = cursor.fetchall()
    return {(documento, linha) for documento, linha in linhas}


def resumo_precisao() -> dict:
    """Precisão medida de verdade: das sugestões revisadas, quantas o
    time confirmou como certas. `precisao_percentual` é `None` (não `0`)
    quando ainda não há nenhuma revisão — não faz sentido mostrar "0% de
    precisão" quando na verdade é "ainda não sabemos"."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("""
            SELECT resultado, COUNT(*) FROM classificacao_contabil_revisoes GROUP BY resultado
        """)
        contagens = dict(cursor.fetchall())

    aceitas = contagens.get("aceita", 0)
    corrigidas = contagens.get("corrigida", 0)
    total = aceitas + corrigidas
    return {
        "total_revisado": total,
        "aceitas": aceitas,
        "corrigidas": corrigidas,
        "precisao_percentual": round(aceitas / total * 100, 1) if total else None,
    }


def revisar(
    usuario: str,
    documento: str,
    linha: str,
    conta_sugerida: str,
    resultado: str,
    conta_correta: str | None = None,
) -> None:
    if resultado not in _RESULTADOS_VALIDOS:
        raise ValueError(f"resultado inválido: {resultado!r} (esperado {_RESULTADOS_VALIDOS!r})")

    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            INSERT INTO classificacao_contabil_revisoes
                (usuario, documento, linha, conta_sugerida, resultado, conta_correta, revisado_em)
            VALUES (:usuario, :documento, :linha, :conta_sugerida, :resultado, :conta_correta, :agora)
            ON CONFLICT (documento, linha) DO UPDATE SET
                usuario = EXCLUDED.usuario,
                conta_sugerida = EXCLUDED.conta_sugerida,
                resultado = EXCLUDED.resultado,
                conta_correta = EXCLUDED.conta_correta,
                revisado_em = EXCLUDED.revisado_em
            """,
            usuario=usuario,
            documento=documento,
            linha=linha,
            conta_sugerida=conta_sugerida,
            resultado=resultado,
            conta_correta=conta_correta,
            agora=datetime.now(UTC),
        )
