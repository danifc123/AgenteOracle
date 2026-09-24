"""Auditoria local de toda chamada de IA que sai da máquina (via
`tools/ia/cliente_protegido.py`) — registra domínio, host de destino e um
hash do conteúdo, nunca o texto puro (evita duplicar dado sensível em mais
um lugar; ainda dá pra provar integridade comparando o hash se precisar
investigar depois). Também registra provedor/modelo/tokens de cada chamada
— é o único ponto por onde passa toda chamada de IA (TI + RH, Ollama e OCI),
então é aqui que dá pra responder "quanto cada modelo está consumindo",
sem precisar espalhar contagem de token pelos agentes que usam o client.

Mesmo padrão de `tools/ti/uso_ia_chamados.py`: tabela própria, criada
sozinha (`CREATE TABLE IF NOT EXISTS`), e nunca pode derrubar o
processamento real por causa de falha ao logar (fail-open) — a proteção de
verdade é o saneamento + a trava de host
(`config.py::validar_ollama_host_seguro`), que continuam fail-closed."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from agente_oracle.config import DominioIA
from agente_oracle.db.connection import DatabaseError, get_postgres_connection

_tabela_garantida = False


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auditoria_ia_externa (
            id BIGSERIAL PRIMARY KEY,
            dominio TEXT NOT NULL,
            host TEXT NOT NULL,
            tamanho_caracteres INTEGER NOT NULL,
            hash_conteudo TEXT NOT NULL,
            criado_em TIMESTAMPTZ NOT NULL
        )
    """)
    # ADD COLUMN IF NOT EXISTS: idempotente tanto pra tabela nova quanto pra
    # uma já existente de antes desses 4 campos existirem.
    cursor.execute("ALTER TABLE auditoria_ia_externa ADD COLUMN IF NOT EXISTS provedor TEXT")
    cursor.execute("ALTER TABLE auditoria_ia_externa ADD COLUMN IF NOT EXISTS modelo TEXT")
    cursor.execute("ALTER TABLE auditoria_ia_externa ADD COLUMN IF NOT EXISTS tokens_entrada INTEGER")
    cursor.execute("ALTER TABLE auditoria_ia_externa ADD COLUMN IF NOT EXISTS tokens_saida INTEGER")
    cursor.execute("ALTER TABLE auditoria_ia_externa ADD COLUMN IF NOT EXISTS tokens_raciocinio INTEGER")
    cursor.execute("ALTER TABLE auditoria_ia_externa ADD COLUMN IF NOT EXISTS usuario_id TEXT")
    _tabela_garantida = True


@dataclass(frozen=True)
class ResumoTokensProvedor:
    provedor: str
    modelo: str
    chamadas: int
    tokens_entrada_total: int
    tokens_saida_total: int
    tokens_raciocinio_total: int


@dataclass(frozen=True)
class ResumoTokensUsuario:
    usuario_id: str
    chamadas: int
    tokens_entrada_total: int
    tokens_saida_total: int
    tokens_raciocinio_total: int


@dataclass(frozen=True)
class ResumoTokensDia:
    data: str  # "YYYY-MM-DD"
    chamadas: int
    tokens_entrada_total: int
    tokens_saida_total: int


def contagem_hoje(dominio: DominioIA) -> int:
    """Quantas chamadas desse domínio já saíram hoje (UTC) — usada pro
    alerta de teto de volume (ver `tools/ia/cliente_protegido.py`).
    Fail-open: erro de Postgres devolve 0 em vez de levantar, nunca
    bloqueia a chamada real por causa disso."""
    try:
        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute(
                """
                SELECT COUNT(*) FROM auditoria_ia_externa
                WHERE dominio = :dominio AND criado_em >= date_trunc('day', now())
                """,
                dominio=dominio,
            )
            (total,) = cursor.fetchone()
        return total
    except DatabaseError:
        return 0


def registrar(
    dominio: DominioIA,
    host: str,
    texto: str,
    provedor: str,
    modelo: str,
    tokens_entrada: int | None,
    tokens_saida: int | None,
    tokens_raciocinio: int | None,
    usuario_id: str,
) -> None:
    """Nunca levanta — falha de auditoria não pode travar o processamento
    real (mesmo espírito de `uso_ia_chamados.registrar`). Grava tamanho +
    hash do texto, não o texto em si. `tokens_entrada`/`tokens_saida`/
    `tokens_raciocinio` podem vir `None` — o Ollama pode omitir em respostas
    parciais, e só o `gpt-oss-120b` tem o conceito de raciocínio separado;
    nada disso significa que a chamada falhou. `usuario_id` é
    `usuario["sub"]` de quem disparou a chamada, ou
    `cliente_protegido.USUARIO_SISTEMA` quando não tem sessão por trás
    (poller, webhook do GLPI)."""
    try:
        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute(
                """
                INSERT INTO auditoria_ia_externa
                    (dominio, host, tamanho_caracteres, hash_conteudo, criado_em,
                     provedor, modelo, tokens_entrada, tokens_saida, tokens_raciocinio, usuario_id)
                VALUES (:dominio, :host, :tamanho, :hash_conteudo, :agora,
                        :provedor, :modelo, :tokens_entrada, :tokens_saida, :tokens_raciocinio, :usuario_id)
                """,
                dominio=dominio,
                host=host,
                tamanho=len(texto),
                hash_conteudo=hashlib.sha256(texto.encode("utf-8")).hexdigest(),
                agora=datetime.now(UTC),
                provedor=provedor,
                modelo=modelo,
                tokens_entrada=tokens_entrada,
                tokens_saida=tokens_saida,
                tokens_raciocinio=tokens_raciocinio,
                usuario_id=usuario_id,
            )
    except DatabaseError:
        pass


def tokens_hoje(dominio: DominioIA) -> int:
    """Soma de tokens de entrada + saída de hoje (UTC) pro domínio — usada
    pro aviso de teto de TOKENS (diferente de `contagem_hoje`, que é por
    número de chamadas). Mesmo fail-open: erro de Postgres devolve 0."""
    try:
        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute(
                """
                SELECT COALESCE(SUM(tokens_entrada), 0) + COALESCE(SUM(tokens_saida), 0)
                FROM auditoria_ia_externa
                WHERE dominio = :dominio AND criado_em >= date_trunc('day', now())
                """,
                dominio=dominio,
            )
            (total,) = cursor.fetchone()
        return int(total)
    except DatabaseError:
        return 0


def resumo_por_provedor(dias: int) -> list[ResumoTokensProvedor]:
    """Volume real de chamadas e tokens dos últimos `dias` dias, agrupado
    por provedor + modelo — a base da página de IA do TI
    (`server/ti/uso_ia.py`, `pages/modulos/ti/provedores/` no frontend).
    `provedor IS NOT NULL` exclui chamadas registradas antes dessa coluna
    existir (ver `ALTER TABLE ... ADD COLUMN` em `_garantir_tabela`) — sem
    esse filtro elas apareceriam como uma linha "vazia" confusa, somando
    chamadas sem nenhum provedor/modelo/token de verdade por trás."""
    desde = datetime.now(UTC) - timedelta(days=dias)
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            SELECT provedor, modelo, COUNT(*),
                   COALESCE(SUM(tokens_entrada), 0), COALESCE(SUM(tokens_saida), 0),
                   COALESCE(SUM(tokens_raciocinio), 0)
            FROM auditoria_ia_externa
            WHERE criado_em >= :desde AND provedor IS NOT NULL
            GROUP BY provedor, modelo
            ORDER BY provedor, modelo
            """,
            desde=desde,
        )
        linhas = cursor.fetchall()
    return [
        ResumoTokensProvedor(
            provedor=provedor,
            modelo=modelo or "",
            chamadas=chamadas,
            tokens_entrada_total=int(tokens_entrada_total),
            tokens_saida_total=int(tokens_saida_total),
            tokens_raciocinio_total=int(tokens_raciocinio_total),
        )
        for provedor, modelo, chamadas, tokens_entrada_total, tokens_saida_total, tokens_raciocinio_total in linhas
    ]


def resumo_por_usuario(dias: int) -> list[ResumoTokensUsuario]:
    """Mesma ideia de `resumo_por_provedor`, agrupado por `usuario_id` em
    vez de provedor/modelo — responde "quem gasta mais" na página de IA do
    TI. Ordena por consumo total DESCENDENTE de propósito (diferente de
    `resumo_por_provedor`, que é alfabético): aqui a ordem em si já é a
    resposta, sem precisar reordenar na tela. Mesmo filtro
    `usuario_id IS NOT NULL` de `resumo_por_provedor`, mesmo motivo:
    exclui chamadas registradas antes dessa coluna existir."""
    desde = datetime.now(UTC) - timedelta(days=dias)
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            SELECT usuario_id, COUNT(*),
                   COALESCE(SUM(tokens_entrada), 0), COALESCE(SUM(tokens_saida), 0),
                   COALESCE(SUM(tokens_raciocinio), 0)
            FROM auditoria_ia_externa
            WHERE criado_em >= :desde AND usuario_id IS NOT NULL
            GROUP BY usuario_id
            ORDER BY COALESCE(SUM(tokens_entrada), 0) + COALESCE(SUM(tokens_saida), 0) DESC
            """,
            desde=desde,
        )
        linhas = cursor.fetchall()
    return [
        ResumoTokensUsuario(
            usuario_id=usuario_id,
            chamadas=chamadas,
            tokens_entrada_total=int(tokens_entrada_total),
            tokens_saida_total=int(tokens_saida_total),
            tokens_raciocinio_total=int(tokens_raciocinio_total),
        )
        for usuario_id, chamadas, tokens_entrada_total, tokens_saida_total, tokens_raciocinio_total in linhas
    ]


def resumo_diario(dias: int) -> list[ResumoTokensDia]:
    """Tokens por dia dos últimos `dias` dias, do mais antigo pro mais
    recente — alimenta o gráfico de tendência da página Tokens do TI
    (`GraficoSerie`, que lê da esquerda pra direita). Diferente de
    `resumo_por_provedor`/`resumo_por_usuario`: aqui não interessa QUEM ou
    O QUÊ, só a evolução no tempo."""
    desde = datetime.now(UTC) - timedelta(days=dias)
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            SELECT to_char(date_trunc('day', criado_em), 'YYYY-MM-DD'), COUNT(*),
                   COALESCE(SUM(tokens_entrada), 0), COALESCE(SUM(tokens_saida), 0)
            FROM auditoria_ia_externa
            WHERE criado_em >= :desde
            GROUP BY date_trunc('day', criado_em)
            ORDER BY date_trunc('day', criado_em) ASC
            """,
            desde=desde,
        )
        linhas = cursor.fetchall()
    return [
        ResumoTokensDia(
            data=data,
            chamadas=chamadas,
            tokens_entrada_total=int(tokens_entrada_total),
            tokens_saida_total=int(tokens_saida_total),
        )
        for data, chamadas, tokens_entrada_total, tokens_saida_total in linhas
    ]
