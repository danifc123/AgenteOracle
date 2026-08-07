"""Trilha de auditoria de eventos de login e administração de contas — tabela
própria, mesmo padrão de `tools/auth/usuarios.py` (`CREATE TABLE IF NOT
EXISTS`, sem migração separada). Existe porque hoje só o ESTADO atual de um
usuário fica salvo (`usuarios.ativo`, `.bloqueado`...) — o HISTÓRICO de quem
fez o quê, quando, não ficava registrado em lugar nenhum, o que dificulta
investigar um incidente depois.

Tipos de evento usados hoje (string livre de propósito, não é enum — abrir
um tipo novo é só chamar `registrar` com uma string nova, sem precisar
editar este arquivo): `login_sucesso`, `login_falha`, `conta_bloqueada`,
`conta_desbloqueada`, `usuario_criado`, `usuario_apagado`.
"""

import json
from datetime import UTC, datetime

from agente_oracle.db.connection import DatabaseError, get_connection

_tabela_garantida = False


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eventos_seguranca (
            id BIGSERIAL PRIMARY KEY,
            tipo VARCHAR NOT NULL,
            usuario_afetado VARCHAR,
            realizado_por VARCHAR,
            detalhes JSONB,
            criado_em TIMESTAMPTZ NOT NULL
        )
    """)
    _tabela_garantida = True


def registrar(
    tipo: str,
    usuario_afetado: str | None = None,
    realizado_por: str | None = None,
    detalhes: dict | None = None,
) -> None:
    """Grava um evento na trilha. Nunca levanta erro pra quem chamou — uma
    falha ao GRAVAR a auditoria (ex: banco momentaneamente indisponível) não
    pode derrubar o fluxo principal (login continua funcionando mesmo que o
    registro do evento falhe). Bugs de programação (ex: `detalhes` não
    serializável) ainda sobem normalmente — só a escrita no banco é
    protegida, não a montagem dos dados."""
    detalhes_json = json.dumps(detalhes) if detalhes is not None else None

    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute(
                """
                INSERT INTO eventos_seguranca (tipo, usuario_afetado, realizado_por, detalhes, criado_em)
                VALUES (:tipo, :usuario_afetado, :realizado_por, :detalhes::jsonb, :criado_em)
                """,
                tipo=tipo,
                usuario_afetado=usuario_afetado,
                realizado_por=realizado_por,
                detalhes=detalhes_json,
                criado_em=datetime.now(UTC),
            )
    except DatabaseError:
        pass


def listar(limite: int = 200) -> list[dict]:
    """Últimos eventos, mais recentes primeiro — usado pela rota
    `GET /api/auth/eventos-seguranca` (restrita ao time de TI)."""
    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            SELECT id, tipo, usuario_afetado, realizado_por, detalhes, criado_em
            FROM eventos_seguranca ORDER BY id DESC LIMIT :limite
            """,
            limite=limite,
        )
        linhas = cursor.fetchall()

    return [
        {
            "id": id_,
            "tipo": tipo,
            "usuario_afetado": usuario_afetado,
            "realizado_por": realizado_por,
            "detalhes": json.loads(detalhes) if isinstance(detalhes, str) else detalhes,
            # `.isoformat()` aqui — mesmo padrão de `server/financeiro/historico.py`
            # (`_historico_para_json`) — `JSONResponse` do Starlette não serializa
            # `datetime` sozinho, precisa virar string antes de chegar na rota.
            "criado_em": criado_em.isoformat(),
        }
        for id_, tipo, usuario_afetado, realizado_por, detalhes, criado_em in linhas
    ]
