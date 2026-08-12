"""Vagas críticas cadastradas pelo time de RH — tabela própria no Postgres
(estado do sistema, sempre nesse banco — ver `db/connection.py`), criada
sozinha (`CREATE TABLE IF NOT EXISTS`) na primeira chamada, sem migração
separada. Mesmo padrão de `tools/financeiro/layouts.py`. Diferente de
layout (escopado por usuário), vaga é do time de RH inteiro — qualquer
membro pode ver/editar qualquer vaga.
"""

from datetime import UTC, datetime

from agente_oracle.db.connection import DatabaseError, eh_erro_violacao_fk, get_postgres_connection

_COLUNAS = "id, titulo, localizacao, ativa, criado_em"

_tabela_garantida = False


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rh_vagas (
            id BIGSERIAL PRIMARY KEY,
            titulo VARCHAR NOT NULL,
            localizacao VARCHAR NOT NULL,
            ativa BOOLEAN NOT NULL DEFAULT TRUE,
            criado_em TIMESTAMPTZ NOT NULL
        )
    """)
    _tabela_garantida = True


def _linha_para_vaga(linha: tuple) -> dict:
    id_, titulo, localizacao, ativa, criado_em = linha
    return {"id": id_, "titulo": titulo, "localizacao": localizacao, "ativa": ativa, "criado_em": criado_em}


class VagaComCandidatosVinculados(Exception):
    """Levantada ao tentar apagar uma vaga que já tem candidato analisado
    vinculado (`rh_candidatos.vaga_id`) — desativar (`ativa=False`) em vez
    de apagar é o caminho pra esse caso."""


def atualizar(
    id_vaga: int, *, titulo: str | None = None, localizacao: str | None = None, ativa: bool | None = None
) -> dict | None:
    campos: dict[str, object] = {}
    trechos_set = []

    if titulo is not None:
        campos["titulo"] = titulo
        trechos_set.append("titulo = :titulo")
    if localizacao is not None:
        campos["localizacao"] = localizacao
        trechos_set.append("localizacao = :localizacao")
    if ativa is not None:
        campos["ativa"] = ativa
        trechos_set.append("ativa = :ativa")

    if not trechos_set:
        return buscar(id_vaga)

    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            f"UPDATE rh_vagas SET {', '.join(trechos_set)} WHERE id = :id RETURNING {_COLUNAS}",
            id=id_vaga,
            **campos,
        )
        linha = cursor.fetchone()

    return _linha_para_vaga(linha) if linha else None


def buscar(id_vaga: int) -> dict | None:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(f"SELECT {_COLUNAS} FROM rh_vagas WHERE id = :id", id=id_vaga)
        linha = cursor.fetchone()
    return _linha_para_vaga(linha) if linha else None


def criar(titulo: str, localizacao: str) -> dict:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            f"""
            INSERT INTO rh_vagas (titulo, localizacao, ativa, criado_em)
            VALUES (:titulo, :localizacao, TRUE, :agora)
            RETURNING {_COLUNAS}
            """,
            titulo=titulo,
            localizacao=localizacao,
            agora=datetime.now(UTC),
        )
        linha = cursor.fetchone()
    return _linha_para_vaga(linha)


def deletar(id_vaga: int) -> bool:
    try:
        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute("DELETE FROM rh_vagas WHERE id = :id", id=id_vaga)
            return cursor.rowcount > 0
    except DatabaseError as erro:
        if eh_erro_violacao_fk(erro):
            raise VagaComCandidatosVinculados(
                "Não é possível apagar: já existem candidatos analisados vinculados a esta vaga. "
                "Desative a vaga em vez de apagar."
            ) from erro
        raise


def listar(*, somente_ativas: bool = False) -> list[dict]:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        filtro = "WHERE ativa = TRUE" if somente_ativas else ""
        cursor.execute(f"SELECT {_COLUNAS} FROM rh_vagas {filtro} ORDER BY criado_em DESC")
        linhas = cursor.fetchall()
    return [_linha_para_vaga(linha) for linha in linhas]
