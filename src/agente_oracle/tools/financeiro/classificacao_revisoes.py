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
do que o time realmente confirma/corrige.

`precedentes_confirmados()` fecha o loop de aprendizado: como nunca
escrevemos no Oracle, uma correção feita aqui sumiria pro sistema no mês
seguinte (mesmo padrão de histórico apareceria sem sugestão de novo) se não
fosse somada de volta no dicionário de sugestão a cada consulta — ver uso em
`server/financeiro/classificacao_contabil.py`."""

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


def precedentes_confirmados() -> list[tuple[str, str, str]]:
    """(documento, linha, conta) de toda revisão com conta confirmada certa
    — aceita (a sugestão em si) ou corrigida com `conta_correta`
    informada. Corrigida sem `conta_correta` fica de fora: sabemos que a
    sugestão era errada, mas não a certa, então não tem o que ensinar."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("""
            SELECT documento, linha,
                   CASE WHEN resultado = 'aceita' THEN conta_sugerida ELSE conta_correta END
            FROM classificacao_contabil_revisoes
            WHERE resultado = 'aceita' OR (resultado = 'corrigida' AND conta_correta IS NOT NULL)
        """)
        return cursor.fetchall()


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
