"""Histórico de todos os achados que a auditoria de dados já encontrou ao
longo do tempo — guardado numa tabela própria (mesmo padrão de
`tools/financeiro/historico.py`/`tools/auditoria/dispensados.py`: `CREATE
TABLE IF NOT EXISTS` na primeira chamada, sem migração separada). Diferente
de `relatorios_historico` (que expira em 15h), este histórico nunca expira —
o objetivo é acumular dado ao longo do tempo, pra eventualmente servir de
contexto/treino de algum agente, não só cache de curto prazo.

`ja_identificados()` é o que faz esta tabela também servir de deduplicação:
`server/auditoria/rotas.py` só chama `salvar()` (e só devolve pro front) os
achados cujo `(modulo, view, campo, valor)` ainda não está aqui e ATIVO — um
problema já identificado e ainda não corrigido não é reapontado a cada
execução (seria gasto de IA à toa pra "descobrir" de novo o que já se sabe).
Se o dado mudou (mesmo que continue errado, com um valor diferente), o
achado é outra tupla e volta a aparecer normalmente. Isso é global (qualquer
usuário, qualquer execução) — diferente de `tools/auditoria/dispensados.py`,
que é por usuário e serve pra "isso na verdade não é problema", não pra
"isso já foi visto".

A coluna `ativo` existe só pra facilitar teste/depuração: `definir_ativo`
deixa um desenvolvedor "desligar" um achado específico (todas as linhas
daquela tupla) sem apagar o registro — desativado, ele não conta mais pra
`ja_identificados`, então a próxima execução da auditoria volta a considerar
aquele valor como candidato e a IA pode reapontá-lo de novo, mesmo sem o
dado ter mudado. É só pra reproduzir o mesmo cenário de teste várias vezes;
ver `server/auth/dependencia.exigir_desenvolvedor`, que restringe isso ao
papel `desenvolvedor`."""

import uuid
from datetime import UTC, datetime

from agente_oracle.agent.auditoria.analise import Achado
from agente_oracle.db.connection import get_postgres_connection

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
            criado_em TIMESTAMPTZ NOT NULL,
            ativo BOOLEAN NOT NULL DEFAULT TRUE
        )
    """)
    # A tabela pode já existir de antes desta coluna ser criada (ambiente já
    # em uso) — `CREATE TABLE IF NOT EXISTS` não adiciona coluna em tabela
    # que já existe, então garante na mão, sem migração separada.
    if not _coluna_ativo_existe(cursor):
        cursor.execute("ALTER TABLE auditoria_historico ADD COLUMN ativo BOOLEAN NOT NULL DEFAULT TRUE")
    _tabela_garantida = True


def _coluna_ativo_existe(cursor) -> bool:
    cursor.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'auditoria_historico' AND column_name = 'ativo'"
    )
    return cursor.fetchone() is not None


def achados_ativos(modulos_liberados: list[str]) -> list[Achado]:
    """Um achado por tupla `(modulo, view, campo, valor)` ATIVA já conhecida
    (com a descrição mais recente registrada pra ela), restrito aos módulos
    liberados — usado por `server/auditoria/rotas.py` pra juntar no
    `GET /api/auditoria` o que já era conhecido (e continua sem ser
    corrigido, por isso nem entrou na análise desta execução) com o que a IA
    encontrou de novo agora, pro dialog mostrar o quadro completo do que
    ainda está pendente, não só a novidade da execução atual.

    `ROW_NUMBER() OVER (PARTITION BY ...)` em vez de `DISTINCT ON`
    (específico do Postgres) — funciona igual em Oracle."""
    if not modulos_liberados:
        return []

    marcadores = ", ".join(f":modulo_{indice}" for indice in range(len(modulos_liberados)))
    binds = {f"modulo_{indice}": modulo for indice, modulo in enumerate(modulos_liberados)}

    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            f"""
            SELECT modulo, view_nome, campo, valor, descricao
            FROM (
                SELECT modulo, view_nome, campo, valor, descricao,
                       ROW_NUMBER() OVER (
                           PARTITION BY modulo, view_nome, campo, valor
                           ORDER BY criado_em DESC
                       ) AS posicao
                FROM auditoria_historico
                WHERE ativo = TRUE AND modulo IN ({marcadores})
            ) recentes
            WHERE posicao = 1
            """,
            **binds,
        )
        linhas = cursor.fetchall()

    return [
        Achado(modulo=modulo, view=view_nome, campo=campo, valor=valor, descricao=descricao)
        for modulo, view_nome, campo, valor, descricao in linhas
    ]


def definir_ativo(modulo: str, view: str, campo: str, valor: str, ativo: bool) -> bool:
    """Ativa/desativa TODAS as linhas do histórico que correspondem a essa
    tupla `(modulo, view, campo, valor)` de uma vez só — é a tupla, não a
    linha individual, que `ja_identificados` usa pra decidir se bloqueia a
    IA de reanalisar aquele valor. Só pra desenvolvedor testar/depurar (ver
    `server/auth/dependencia.exigir_desenvolvedor`). Devolve True se
    encontrou e atualizou alguma linha."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            UPDATE auditoria_historico
            SET ativo = :ativo
            WHERE modulo = :modulo AND view_nome = :view_nome AND campo = :campo AND valor = :valor
            """,
            ativo=ativo,
            modulo=modulo,
            view_nome=view,
            campo=campo,
            valor=valor,
        )
        return cursor.rowcount > 0


def ja_identificados() -> set[tuple[str, str, str, str]]:
    """Todo achado `(modulo, view, campo, valor)` ATIVO já registrado alguma
    vez, de qualquer execução e qualquer usuário — usado por
    `server/auditoria/rotas.py` (via `filtrar_valores_conhecidos`) pra tirar
    esses valores dos perfis ANTES de mandar pra IA, evitando gastar uma
    chamada de IA pra "redescobrir" um problema que já se sabe que existe e
    ainda não foi corrigido. Global de propósito: uma vez identificado por
    qualquer execução, não faz sentido gastar IA de novo nele pra ninguém.
    Achado desativado (`definir_ativo(..., ativo=False)`) não conta aqui —
    volta a ser tratado como "novo" na próxima execução."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "SELECT DISTINCT modulo, view_nome, campo, valor FROM auditoria_historico WHERE ativo = TRUE"
        )
        linhas = cursor.fetchall()
    return {(modulo, view, campo, valor) for modulo, view, campo, valor in linhas}


def listar(modulos_liberados: list[str], incluir_desativados: bool = False, limite: int = 200) -> list[dict]:
    """Achados já registrados, do mais recente pro mais antigo, restritos aos
    módulos que quem está consultando tem acesso — mesma regra de RBAC do
    `GET /api/auditoria` ao vivo, pra nunca vazar achado de um módulo sem
    permissão através do histórico.

    `incluir_desativados` é pensado pra ser `True` só pra quem tem o papel
    `desenvolvedor` (ver `server/auditoria/rotas.py`): achado desativado
    (`definir_ativo(..., ativo=False)`) é um detalhe interno de
    teste/depuração, não algo que o usuário comum deveria ver ou precisar
    entender — pra ele, esse achado simplesmente nunca existiu."""
    if not modulos_liberados:
        return []

    marcadores = ", ".join(f":modulo_{indice}" for indice in range(len(modulos_liberados)))
    binds = {f"modulo_{indice}": modulo for indice, modulo in enumerate(modulos_liberados)}
    clausula_ativo = "" if incluir_desativados else "AND ativo = TRUE"

    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            f"""
            SELECT execucao_id, usuario_id, modulo, view_nome, campo, valor, descricao, criado_em, ativo
            FROM auditoria_historico
            WHERE modulo IN ({marcadores}) {clausula_ativo}
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
            "ativo": ativo,
        }
        for execucao_id, usuario_id, modulo, view_nome, campo, valor, descricao, criado_em, ativo in linhas
    ]


def salvar(usuario_id: str, achados: list[Achado]) -> str | None:
    """Registra todos os achados de uma execução da auditoria, marcados com o
    mesmo `execucao_id` (permite agrupar depois quem veio da mesma rodada).
    Sem achado nenhum, não grava nada — devolve None nesse caso."""
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
