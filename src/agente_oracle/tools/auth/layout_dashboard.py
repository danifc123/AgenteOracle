"""Layout de indicadores da Home de cada usuário — lista ORDENADA de itens
(a ordem do array já É a ordem de exibição, sem coluna `posicao`
separada). Uma linha por `(usuario_id, modulo)`, não uma linha por widget.

Desenhado por `modulo` (não fixo em "ti"), mesmo motivo de
`tools/auth/restricoes_filial.py`: RH/Financeiro/Estoque reaproveitam a
mesma tabela no futuro sem migração nova — só chamar com outro `modulo`.
O que cada item SIGNIFICA (formato de cada entrada, catálogo, default,
gate de desenvolvedor, deduplicação por id) é conhecimento de quem chama
(`server/ti/dashboard.py`), não desta camada — aqui só entra/sai
`list[dict]` como veio, sem inspecionar o conteúdo de cada item.

Mesmo padrão de `tools/financeiro/layouts.py`/`tools/auth/usuarios.py`:
tabela própria, criada sozinha (`CREATE TABLE IF NOT EXISTS`), sem migração
separada."""

import json
from datetime import UTC, datetime

from agente_oracle.db.connection import get_postgres_connection

_tabela_garantida = False


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS layouts_dashboard (
            id BIGSERIAL PRIMARY KEY,
            usuario_id BIGINT NOT NULL,
            modulo VARCHAR NOT NULL,
            widgets JSONB NOT NULL,
            atualizado_em TIMESTAMPTZ NOT NULL,
            UNIQUE (usuario_id, modulo)
        )
    """)
    _tabela_garantida = True


def _carregar_json(valor) -> list[dict]:
    return json.loads(valor) if isinstance(valor, str) else valor


def layout_dashboard(usuario_id: int, modulo: str) -> list[dict] | None:
    """`None` = usuário nunca salvou nada nesse módulo — quem chama decide o default."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "SELECT widgets FROM layouts_dashboard WHERE usuario_id = :usuario_id AND modulo = :modulo",
            usuario_id=usuario_id,
            modulo=modulo,
        )
        linha = cursor.fetchone()

    return _carregar_json(linha[0]) if linha else None


def definir_layout_dashboard(usuario_id: int, modulo: str, widgets: list[dict]) -> list[dict]:
    """Substitui a lista inteira (semântica de "salvar a seleção/ordem
    atual", igual `restricoes_filial.definir_bloqueadas`) — preserva a
    ORDEM recebida (ao contrário de lá, não ordena alfabeticamente: aqui a
    ordem é o dado) exatamente como veio; quem chama já filtrou/deduplicou
    antes (ver `server/ti/dashboard.py::_layout_visivel`), essa camada não
    sabe o que faria dois itens serem "iguais". Devolve a lista que de fato
    ficou salva."""
    agora = datetime.now(UTC)

    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            INSERT INTO layouts_dashboard (usuario_id, modulo, widgets, atualizado_em)
            VALUES (:usuario_id, :modulo, :widgets::jsonb, :atualizado_em)
            ON CONFLICT (usuario_id, modulo)
            DO UPDATE SET widgets = :widgets::jsonb, atualizado_em = :atualizado_em
            """,
            usuario_id=usuario_id,
            modulo=modulo,
            widgets=json.dumps(widgets),
            atualizado_em=agora,
        )

    return widgets


def remover_usuario(usuario_id: int) -> None:
    """Limpa o layout salvo (de qualquer módulo) de um usuário — chamada por
    `tools/auth/usuarios.py::deletar_usuario` antes de apagar o usuário,
    pra não deixar linha órfã na tabela."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("DELETE FROM layouts_dashboard WHERE usuario_id = :usuario_id", usuario_id=usuario_id)
