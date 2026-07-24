"""Layouts salvos da tela "Criar Relatório" — cada layout guarda a seleção de
colunas (por tabela), os filtros preenchidos e as filiais escolhidas, pra o
usuário recarregar depois sem remontar tudo na mão.

Mesmo padrão de `tools/financeiro/historico.py` e `tools/auth/usuarios.py`:
tabela própria no mesmo banco relacional configurado em DB_BACKEND, criada
sozinha (`CREATE TABLE IF NOT EXISTS`) na primeira chamada, sem migração
separada. Diferente do histórico, aqui os registros são escopados por usuário
(`usuario_id`, extraído do JWT em `exigir_usuario`) — cada um só vê/mexe nos
próprios layouts.
"""

import json
from datetime import datetime, timezone

from agente_oracle.db.connection import DatabaseError, eh_erro_valor_duplicado, get_connection

_COLUNAS = (
    "id, usuario_id, nome, colunas_selecionadas, valores_filtros, filiais_selecionadas, criado_em, atualizado_em"
)

_tabela_garantida = False


class LayoutJaExiste(Exception):
    """Levantada quando `criar`/`atualizar` tentam usar um nome que o mesmo
    usuário já usa em outro layout (constraint única em usuario_id+nome)."""


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS relatorio_layouts (
            id BIGSERIAL PRIMARY KEY,
            usuario_id BIGINT NOT NULL,
            nome VARCHAR NOT NULL,
            colunas_selecionadas JSONB NOT NULL,
            valores_filtros JSONB NOT NULL,
            filiais_selecionadas JSONB NOT NULL,
            criado_em TIMESTAMPTZ NOT NULL,
            atualizado_em TIMESTAMPTZ NOT NULL,
            UNIQUE (usuario_id, nome)
        )
    """)
    _tabela_garantida = True


def _carregar_json(valor):
    return json.loads(valor) if isinstance(valor, str) else valor


def _linha_para_layout(linha: tuple) -> dict:
    id_, usuario_id, nome, colunas_selecionadas, valores_filtros, filiais_selecionadas, criado_em, atualizado_em = linha
    return {
        "id": id_,
        "usuario_id": usuario_id,
        "nome": nome,
        "colunas_selecionadas": _carregar_json(colunas_selecionadas),
        "valores_filtros": _carregar_json(valores_filtros),
        "filiais_selecionadas": _carregar_json(filiais_selecionadas),
        "criado_em": criado_em,
        "atualizado_em": atualizado_em,
    }


def criar(
    usuario_id: int,
    nome: str,
    colunas_selecionadas: dict[str, list[str]],
    valores_filtros: dict[str, str],
    filiais_selecionadas: list[str],
) -> dict:
    agora = datetime.now(timezone.utc)

    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute(
                f"""
                INSERT INTO relatorio_layouts
                    (usuario_id, nome, colunas_selecionadas, valores_filtros, filiais_selecionadas, criado_em, atualizado_em)
                VALUES
                    (:usuario_id, :nome, :colunas_selecionadas::jsonb, :valores_filtros::jsonb, :filiais_selecionadas::jsonb, :agora, :agora)
                RETURNING {_COLUNAS}
                """,
                usuario_id=usuario_id,
                nome=nome,
                colunas_selecionadas=json.dumps(colunas_selecionadas),
                valores_filtros=json.dumps(valores_filtros),
                filiais_selecionadas=json.dumps(filiais_selecionadas),
                agora=agora,
            )
            linha = cursor.fetchone()
    except DatabaseError as erro:
        if eh_erro_valor_duplicado(erro):
            raise LayoutJaExiste(f"Você já tem um layout chamado '{nome}'.") from erro
        raise

    return _linha_para_layout(linha)


def listar(usuario_id: int) -> list[dict]:
    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            f"SELECT {_COLUNAS} FROM relatorio_layouts WHERE usuario_id = :usuario_id ORDER BY nome",
            usuario_id=usuario_id,
        )
        linhas = cursor.fetchall()
    return [_linha_para_layout(linha) for linha in linhas]


def atualizar(
    usuario_id: int,
    id_layout: str,
    *,
    nome: str | None = None,
    colunas_selecionadas: dict[str, list[str]] | None = None,
    valores_filtros: dict[str, str] | None = None,
    filiais_selecionadas: list[str] | None = None,
) -> dict | None:
    try:
        id_numerico = int(id_layout)
    except ValueError:
        return None

    campos: dict[str, object] = {"atualizado_em": datetime.now(timezone.utc)}
    trechos_set = ["atualizado_em = :atualizado_em"]

    if nome is not None:
        campos["nome"] = nome
        trechos_set.append("nome = :nome")
    if colunas_selecionadas is not None:
        campos["colunas_selecionadas"] = json.dumps(colunas_selecionadas)
        trechos_set.append("colunas_selecionadas = :colunas_selecionadas::jsonb")
    if valores_filtros is not None:
        campos["valores_filtros"] = json.dumps(valores_filtros)
        trechos_set.append("valores_filtros = :valores_filtros::jsonb")
    if filiais_selecionadas is not None:
        campos["filiais_selecionadas"] = json.dumps(filiais_selecionadas)
        trechos_set.append("filiais_selecionadas = :filiais_selecionadas::jsonb")

    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute(
                f"""
                UPDATE relatorio_layouts SET {", ".join(trechos_set)}
                WHERE id = :id AND usuario_id = :usuario_id
                RETURNING {_COLUNAS}
                """,
                id=id_numerico,
                usuario_id=usuario_id,
                **campos,
            )
            linha = cursor.fetchone()
    except DatabaseError as erro:
        if eh_erro_valor_duplicado(erro):
            raise LayoutJaExiste(f"Você já tem um layout chamado '{nome}'.") from erro
        raise

    return _linha_para_layout(linha) if linha else None


def deletar(usuario_id: int, id_layout: str) -> bool:
    try:
        id_numerico = int(id_layout)
    except ValueError:
        return False

    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "DELETE FROM relatorio_layouts WHERE id = :id AND usuario_id = :usuario_id",
            id=id_numerico,
            usuario_id=usuario_id,
        )
        return cursor.rowcount > 0
