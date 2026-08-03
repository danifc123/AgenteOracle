"""Histórico de todos os achados que a auditoria de dados já encontrou ao
longo do tempo — guardado numa tabela própria (mesmo padrão de
`tools/financeiro/historico.py`/`tools/auditoria/dispensados.py`: `CREATE
TABLE IF NOT EXISTS` na primeira chamada, sem migração separada). Diferente
de `relatorios_historico` (que expira em 15h), este histórico nunca expira —
o objetivo é acumular dado ao longo do tempo, pra eventualmente servir de
contexto/treino de algum agente, não só cache de curto prazo.

Guarda TODO achado fundamentado que a IA já apontou, mesmo os que o usuário
depois dispensou (`tools/auditoria/dispensados.py`) — dispensar só afeta o
que aparece na tela seguinte, não apaga o registro de que aquele achado já
foi sugerido um dia."""

import uuid
from datetime import datetime, timezone

from agente_oracle.agent.auditoria.analise import Achado
from agente_oracle.db.connection import get_connection

_tabela_garantida = False


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auditoria_historico (
            id BIGSERIAL PRIMARY KEY,
            execucao_id VARCHAR NOT NULL,
            usuario_id VARCHAR NOT NULL,
            modulo VARCHAR NOT NULL,
            view_nome VARCHAR NOT NULL,
            campo VARCHAR NOT NULL,
            valor VARCHAR NOT NULL,
            descricao TEXT NOT NULL,
            criado_em TIMESTAMPTZ NOT NULL
        )
    """)
    _tabela_garantida = True


def salvar(usuario_id: str, achados: list[Achado]) -> str | None:
    """Registra todos os achados de uma execução da auditoria, marcados com o
    mesmo `execucao_id` (permite agrupar depois quem veio da mesma rodada).
    Sem achado nenhum, não grava nada — devolve None nesse caso."""
    if not achados:
        return None

    execucao_id = uuid.uuid4().hex
    agora = datetime.now(timezone.utc)

    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        for achado in achados:
            cursor.execute(
                """
                INSERT INTO auditoria_historico
                    (execucao_id, usuario_id, modulo, view_nome, campo, valor, descricao, criado_em)
                VALUES
                    (:execucao_id, :usuario_id, :modulo, :view_nome, :campo, :valor, :descricao, :criado_em)
                """,
                execucao_id=execucao_id,
                usuario_id=usuario_id,
                modulo=achado.modulo,
                view_nome=achado.view,
                campo=achado.campo,
                valor=achado.valor,
                descricao=achado.descricao,
                criado_em=agora,
            )

    return execucao_id


def listar(modulos_liberados: list[str], limite: int = 200) -> list[dict]:
    """Achados já registrados, do mais recente pro mais antigo, restritos aos
    módulos que quem está consultando tem acesso — mesma regra de RBAC do
    `GET /api/auditoria` ao vivo, pra nunca vazar achado de um módulo sem
    permissão através do histórico."""
    if not modulos_liberados:
        return []

    marcadores = ", ".join(f":modulo_{indice}" for indice in range(len(modulos_liberados)))
    binds = {f"modulo_{indice}": modulo for indice, modulo in enumerate(modulos_liberados)}

    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            f"""
            SELECT execucao_id, usuario_id, modulo, view_nome, campo, valor, descricao, criado_em
            FROM auditoria_historico
            WHERE modulo IN ({marcadores})
            ORDER BY criado_em DESC
            FETCH FIRST {limite} ROWS ONLY
            """,
            **binds,
        )
        linhas = cursor.fetchall()

    return [
        {
            "execucao_id": execucao_id,
            "usuario_id": usuario_id,
            "modulo": modulo,
            "view": view_nome,
            "campo": campo,
            "valor": valor,
            "descricao": descricao,
            "criado_em": criado_em.isoformat(),
        }
        for execucao_id, usuario_id, modulo, view_nome, campo, valor, descricao, criado_em in linhas
    ]
