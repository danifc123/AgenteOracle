"""Histórico de achados de segurança que o agente de detecção
(`agent/ti/deteccao_seguranca.py`) já encontrou ao longo do tempo — mesmo
padrão de `tools/auditoria/historico.py` (tabela própria, `CREATE TABLE IF
NOT EXISTS`, nunca expira, serve de deduplicação via `ja_identificados`
pra não gastar IA "redescobrindo" um achado que já existe e ainda não foi
tratado).

Diferente da Auditoria de dado (que dedup por `modulo/view/campo/valor`),
aqui a chave é `(usuario_alvo, sistema, tipo)` — um mesmo usuário com o
mesmo tipo de achado no mesmo sistema (`agente_oracle`/`protheus`) não é
reapontado a cada execução enquanto continuar ativo. `sistema` entra na
chave porque um achado no Protheus e um no AgenteOracle pro mesmo usuário
são incidentes distintos, com respostas diferentes."""

import uuid
from datetime import UTC, datetime

from agente_oracle.agent.ti.deteccao_seguranca import AchadoSeguranca
from agente_oracle.db.connection import get_postgres_connection

_tabela_garantida = False


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ti_seguranca_historico (
            id BIGSERIAL PRIMARY KEY,
            execucao_id VARCHAR NOT NULL,
            usuario_id VARCHAR NOT NULL,
            usuario_alvo VARCHAR NOT NULL,
            sistema VARCHAR NOT NULL DEFAULT 'agente_oracle',
            tipo VARCHAR NOT NULL,
            descricao TEXT NOT NULL,
            evidencia TEXT NOT NULL,
            criado_em TIMESTAMPTZ NOT NULL,
            ativo BOOLEAN NOT NULL DEFAULT TRUE
        )
    """)
    # A tabela pode já existir de antes do campo `sistema` existir —
    # `CREATE TABLE IF NOT EXISTS` não adiciona coluna em tabela que já
    # existe, então garante na mão, sem migração separada.
    cursor.execute(
        "ALTER TABLE ti_seguranca_historico ADD COLUMN IF NOT EXISTS sistema VARCHAR NOT NULL DEFAULT 'agente_oracle'"
    )
    _tabela_garantida = True


def achados_ativos() -> list[AchadoSeguranca]:
    """Um achado por `(usuario_alvo, sistema, tipo)` ATIVO já conhecido
    (com a descrição/evidência mais recente registrada pra ele) — usado
    por `server/ti/seguranca.py` pra juntar no `GET /api/ti/seguranca` o
    que já era conhecido (e continua sem ser tratado) com o que a IA
    encontrou de novo agora."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("""
            SELECT usuario_alvo, sistema, tipo, descricao, evidencia
            FROM (
                SELECT usuario_alvo, sistema, tipo, descricao, evidencia,
                       ROW_NUMBER() OVER (
                           PARTITION BY usuario_alvo, sistema, tipo ORDER BY criado_em DESC
                       ) AS posicao
                FROM ti_seguranca_historico
                WHERE ativo = TRUE
            ) recentes
            WHERE posicao = 1
        """)
        linhas = cursor.fetchall()

    return [
        AchadoSeguranca(
            usuario=usuario_alvo, sistema=sistema, tipo=tipo, descricao=descricao, evidencia=evidencia
        )
        for usuario_alvo, sistema, tipo, descricao, evidencia in linhas
    ]


def definir_ativo(usuario_alvo: str, sistema: str, tipo: str, ativo: bool) -> bool:
    """Ativa/desativa TODAS as linhas do histórico dessa tupla
    `(usuario_alvo, sistema, tipo)` de uma vez — usado por "dispensar"
    (desativa, pra IA poder reencontrar o mesmo padrão numa execução
    futura se ele persistir). Devolve True se encontrou e atualizou
    alguma linha."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            UPDATE ti_seguranca_historico SET ativo = :ativo
            WHERE usuario_alvo = :usuario_alvo AND sistema = :sistema AND tipo = :tipo
            """,
            ativo=ativo,
            usuario_alvo=usuario_alvo,
            sistema=sistema,
            tipo=tipo,
        )
        return cursor.rowcount > 0


def ja_identificados() -> set[tuple[str, str, str]]:
    """Toda tupla `(usuario_alvo, sistema, tipo)` ATIVA já registrada
    alguma vez — tirada dos perfis antes de chamar a IA, mesma lógica de
    `tools/auditoria/historico.ja_identificados`."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "SELECT DISTINCT usuario_alvo, sistema, tipo FROM ti_seguranca_historico WHERE ativo = TRUE"
        )
        linhas = cursor.fetchall()
    return {(usuario_alvo, sistema, tipo) for usuario_alvo, sistema, tipo in linhas}


def listar(incluir_desativados: bool = False, limite: int = 200) -> list[dict]:
    """Achados já registrados, do mais recente pro mais antigo.
    `incluir_desativados` é pensado pra ser `True` só pra papel
    `desenvolvedor` (mesma regra de `tools/auditoria/historico.listar`)."""
    clausula_ativo = "" if incluir_desativados else "WHERE ativo = TRUE"

    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(f"""
            SELECT execucao_id, usuario_id, usuario_alvo, sistema, tipo, descricao, evidencia, criado_em, ativo
            FROM ti_seguranca_historico
            {clausula_ativo}
            ORDER BY criado_em DESC
            FETCH FIRST {limite} ROWS ONLY
        """)
        linhas = cursor.fetchall()

    return [
        {
            "execucao_id": execucao_id,
            "usuario_id": usuario_id,
            "usuario_alvo": usuario_alvo,
            "sistema": sistema,
            "tipo": tipo,
            "descricao": descricao,
            "evidencia": evidencia,
            "criado_em": criado_em.isoformat(),
            "ativo": ativo,
        }
        for execucao_id, usuario_id, usuario_alvo, sistema, tipo, descricao, evidencia, criado_em, ativo in linhas
    ]


def salvar(usuario_id: str, achados: list[AchadoSeguranca]) -> str | None:
    """Registra todos os achados de uma execução, marcados com o mesmo
    `execucao_id`. Sem achado nenhum, não grava nada — devolve None."""
    if not achados:
        return None

    execucao_id = uuid.uuid4().hex
    agora = datetime.now(UTC)

    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        for achado in achados:
            cursor.execute(
                """
                INSERT INTO ti_seguranca_historico
                    (execucao_id, usuario_id, usuario_alvo, sistema, tipo, descricao, evidencia, criado_em)
                VALUES
                    (:execucao_id, :usuario_id, :usuario_alvo, :sistema, :tipo, :descricao, :evidencia, :criado_em)
                """,
                execucao_id=execucao_id,
                usuario_id=usuario_id,
                usuario_alvo=achado.usuario,
                sistema=achado.sistema,
                tipo=achado.tipo,
                descricao=achado.descricao,
                evidencia=achado.evidencia,
                criado_em=agora,
            )

    return execucao_id
