"""Pool de candidatos analisados pela IA — tabela própria no Postgres,
mesmo padrão de `tools/financeiro/layouts.py` (`CREATE TABLE IF NOT
EXISTS`, sem migração separada).

Modelo novo (2026-08, substituindo o de "vaga cadastrada + score fixo
contra 6 dimensões"): todo currículo analisado com sucesso vira candidato
no pool, com um resumo de perfil escrito pela IA
(`agent/rh/perfil_candidato.py`) e um embedding desse resumo
(`agent/rh/embeddings.py`) — não tem mais gate de compatibilidade mínima
nem vínculo com uma vaga específica. A busca por candidato ideal pra uma
vaga acontece depois, sob demanda, em `agent/rh/busca_candidatos.py`
(`listar_para_busca`, abaixo, é o que alimenta essa busca).

O currículo original fica guardado (`arquivo`, `BYTEA`) pra poder ser
baixado de novo depois — ver `buscar_arquivo`.
"""

import json
import unicodedata
from datetime import UTC, datetime

from ollama import AsyncClient

from agente_oracle.agent.rh.embeddings import gerar_embedding
from agente_oracle.agent.rh.perfil_candidato import gerar_perfil
from agente_oracle.db.connection import get_postgres_connection
from agente_oracle.tools.rh.extracao_curriculo import extrair_texto

_COLUNAS_CANDIDATO = "id, nome, resumo_perfil, perfil_estruturado, status, criado_em"
_COLUNAS_BUSCA = "id, nome, resumo_perfil, perfil_estruturado, embedding"

_tabela_garantida = False


# _carregar_json, _garantir_tabela e _linha_para_candidato são usadas por
# mais de uma função pública — bloco compartilhado, em ordem alfabética,
# antes das públicas que dependem delas.
def _carregar_json(valor):
    return json.loads(valor) if isinstance(valor, str) else valor


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rh_candidatos (
            id BIGSERIAL PRIMARY KEY,
            nome VARCHAR NOT NULL,
            resumo_perfil TEXT NOT NULL,
            perfil_estruturado JSONB NOT NULL DEFAULT '{}',
            embedding JSONB NOT NULL,
            nome_arquivo VARCHAR NOT NULL,
            tipo_arquivo VARCHAR NOT NULL,
            arquivo BYTEA NOT NULL,
            status VARCHAR NOT NULL DEFAULT 'ativo',
            criado_em TIMESTAMPTZ NOT NULL
        )
    """)
    # A tabela pode já existir de antes de `perfil_estruturado` existir
    # (ambiente já em uso) — `CREATE TABLE IF NOT EXISTS` não adiciona
    # coluna em tabela que já existe, então garante na mão, sem migração
    # separada. Candidato já cadastrado antes disso fica com `{}` (só o
    # resumo livre continua disponível pra ele, sem os campos granulares).
    cursor.execute(
        "ALTER TABLE rh_candidatos ADD COLUMN IF NOT EXISTS perfil_estruturado JSONB NOT NULL DEFAULT '{}'"
    )
    _tabela_garantida = True


def _linha_para_candidato(linha: tuple) -> dict:
    id_, nome, resumo_perfil, perfil_estruturado, status, criado_em = linha
    return {
        "id": id_,
        "nome": nome,
        "resumo_perfil": resumo_perfil,
        "perfil_estruturado": _carregar_json(perfil_estruturado),
        "status": status,
        "criado_em": criado_em,
    }


def atualizar_status(id_candidato: int, status: str) -> dict | None:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            f"UPDATE rh_candidatos SET status = :status WHERE id = :id RETURNING {_COLUNAS_CANDIDATO}",
            id=id_candidato,
            status=status,
        )
        linha = cursor.fetchone()
    return _linha_para_candidato(linha) if linha else None


def buscar_arquivo(id_candidato: int) -> dict | None:
    """Currículo original (nome/tipo/bytes) — usado só pela rota de
    download, nunca devolvido junto da listagem (evita carregar o binário
    à toa numa resposta JSON que ninguém vai usar)."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "SELECT nome_arquivo, tipo_arquivo, arquivo FROM rh_candidatos WHERE id = :id",
            id=id_candidato,
        )
        linha = cursor.fetchone()
    return _linha_para_arquivo(linha) if linha else None


# _linha_para_arquivo só é usada por buscar_arquivo, logo depois dela.
def _linha_para_arquivo(linha: tuple) -> dict:
    nome_arquivo, tipo_arquivo, arquivo = linha
    return {"nome_arquivo": nome_arquivo, "tipo_arquivo": tipo_arquivo, "arquivo": bytes(arquivo)}


async def criar_candidato(
    ollama_client: AsyncClient,
    modelo: str,
    modelo_embedding: str,
    nome_arquivo: str,
    conteudo_arquivo: bytes,
) -> dict:
    """Extrai o texto do currículo, pede um resumo de perfil pra IA, gera o
    embedding desse resumo, e cadastra o candidato no pool — sempre, sem
    gate de compatibilidade mínima (isso não existe mais aqui; a
    compatibilidade com uma vaga é calculada sob demanda em
    `agent/rh/busca_candidatos.py`, não no momento do cadastro). Levanta
    `ArquivoCurriculoInvalido` (arquivo ilegível) ou `AnaliseIndisponivel`
    (IA fora do ar/resposta inválida) sem cadastrar nada nesses casos."""
    texto_curriculo = extrair_texto(nome_arquivo, conteudo_arquivo)
    perfil = await gerar_perfil(ollama_client, modelo, texto_curriculo)
    embedding = await gerar_embedding(ollama_client, modelo_embedding, perfil.resumo_objetivo)
    tipo_arquivo = "pdf" if nome_arquivo.lower().endswith(".pdf") else "docx"

    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            f"""
            INSERT INTO rh_candidatos
                (nome, resumo_perfil, perfil_estruturado, embedding, nome_arquivo, tipo_arquivo,
                 arquivo, status, criado_em)
            VALUES
                (:nome, :resumo_perfil, :perfil_estruturado::jsonb, :embedding::jsonb, :nome_arquivo,
                 :tipo_arquivo, :arquivo, 'ativo', :agora)
            RETURNING {_COLUNAS_CANDIDATO}
            """,
            nome=perfil.nome_candidato,
            resumo_perfil=perfil.resumo_objetivo,
            perfil_estruturado=json.dumps(perfil.campos_estruturados()),
            embedding=json.dumps(embedding),
            nome_arquivo=nome_arquivo,
            tipo_arquivo=tipo_arquivo,
            arquivo=conteudo_arquivo,
            agora=datetime.now(UTC),
        )
        linha = cursor.fetchone()
    return _linha_para_candidato(linha)


def listar(*, status: str | None = None) -> list[dict]:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        if status:
            cursor.execute(
                f"SELECT {_COLUNAS_CANDIDATO} FROM rh_candidatos WHERE status = :status ORDER BY criado_em DESC",
                status=status,
            )
        else:
            cursor.execute(f"SELECT {_COLUNAS_CANDIDATO} FROM rh_candidatos ORDER BY criado_em DESC")
        linhas = cursor.fetchall()
    return [_linha_para_candidato(linha) for linha in linhas]


def listar_para_busca() -> list[dict]:
    """Candidatos `ativo` com o embedding do perfil — só os campos que
    `agent/rh/busca_candidatos.py` precisa pra fazer a busca (retrieval +
    ranking), não a listagem completa da tela. Colapsa candidato com nome
    repetido (currículo reenviado, upload em duplicidade) numa linha só,
    pra busca nunca rankear a mesma pessoa duas vezes."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            f"SELECT {_COLUNAS_BUSCA} FROM rh_candidatos WHERE status = 'ativo' ORDER BY criado_em DESC"
        )
        linhas = cursor.fetchall()
    return _sem_duplicatas([_linha_para_busca(linha) for linha in linhas])


# _linha_para_busca e _sem_duplicatas só são usadas por listar_para_busca,
# logo depois dela, em ordem alfabética entre si.
def _linha_para_busca(linha: tuple) -> dict:
    id_, nome, resumo_perfil, perfil_estruturado, embedding = linha
    return {
        "id": id_,
        "nome": nome,
        "resumo_perfil": resumo_perfil,
        "perfil_estruturado": _carregar_json(perfil_estruturado),
        "embedding": _carregar_json(embedding),
    }


def _sem_duplicatas(candidatos: list[dict]) -> list[dict]:
    """Mantém só a primeira ocorrência de cada nome normalizado — assume
    que `candidatos` já vem ordenado por `criado_em DESC`, então "primeira
    ocorrência" é sempre a análise mais recente daquela pessoa."""
    vistos = set()
    resultado = []
    for candidato in candidatos:
        chave = _nome_normalizado(candidato["nome"])
        if chave in vistos:
            continue
        vistos.add(chave)
        resultado.append(candidato)
    return resultado


# _nome_normalizado só é usada por _sem_duplicatas, logo depois dela.
def _nome_normalizado(nome: str) -> str:
    """Normaliza pra comparar "é a mesma pessoa": ignora acento, caixa e
    espaço repetido/nas pontas — só pra decidir duplicidade, nunca pra
    exibição."""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    return " ".join(sem_acento.casefold().split())
