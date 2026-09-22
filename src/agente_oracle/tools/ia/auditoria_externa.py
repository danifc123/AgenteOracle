"""Auditoria local de toda chamada de IA que sai da máquina (via
`tools/ia/cliente_protegido.py`) — registra domínio, host de destino e um
hash do conteúdo, nunca o texto puro (evita duplicar dado sensível em mais
um lugar; ainda dá pra provar integridade comparando o hash se precisar
investigar depois).

Mesmo padrão de `tools/ti/uso_ia_chamados.py`: tabela própria, criada
sozinha (`CREATE TABLE IF NOT EXISTS`), e nunca pode derrubar o
processamento real por causa de falha ao logar (fail-open) — a proteção de
verdade é o saneamento + a trava de host
(`config.py::validar_ollama_host_seguro`), que continuam fail-closed."""

import hashlib
from datetime import UTC, datetime

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
    _tabela_garantida = True


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


def registrar(dominio: DominioIA, host: str, texto: str) -> None:
    """Nunca levanta — falha de auditoria não pode travar o processamento
    real (mesmo espírito de `uso_ia_chamados.registrar`). Grava tamanho +
    hash do texto, não o texto em si."""
    try:
        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute(
                """
                INSERT INTO auditoria_ia_externa
                    (dominio, host, tamanho_caracteres, hash_conteudo, criado_em)
                VALUES (:dominio, :host, :tamanho, :hash_conteudo, :agora)
                """,
                dominio=dominio,
                host=host,
                tamanho=len(texto),
                hash_conteudo=hashlib.sha256(texto.encode("utf-8")).hexdigest(),
                agora=datetime.now(UTC),
            )
    except DatabaseError:
        pass
