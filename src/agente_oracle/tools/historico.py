import hashlib
import re
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from agente_oracle.db.mongo import get_colecao_historico

_SELECT_FROM_REGEX = re.compile(r"^SELECT\s+(.*?)\s+FROM\s", re.IGNORECASE | re.DOTALL)

TEMPO_EXPIRACAO = timedelta(hours=15)


def hash_sql(sql_validado: str) -> str:
    """Normaliza o SQL para uma forma canônica e gera um hash estável, usado
    como chave de deduplicação: dois SQLs equivalentes (mesmas colunas em
    ordem diferente, espaçamento ou maiúsculas/minúsculas diferentes) geram o
    mesmo hash. Não altera o SQL que de fato roda no Oracle — só a versão
    usada para comparação."""
    sql_normalizado = " ".join(sql_validado.split()).upper()

    correspondencia = _SELECT_FROM_REGEX.match(sql_normalizado)
    if correspondencia:
        colunas = sorted(coluna.strip() for coluna in correspondencia.group(1).split(","))
        sql_normalizado = (
            sql_normalizado[: correspondencia.start(1)]
            + ", ".join(colunas)
            + sql_normalizado[correspondencia.end(1) :]
        )

    return hashlib.sha256(sql_normalizado.encode("utf-8")).hexdigest()


def buscar_por_sql(sql_validado: str) -> dict | None:
    return get_colecao_historico().find_one({"hash_sql": hash_sql(sql_validado)})


def salvar(sql_validado: str, titulo: str, colunas: list[str], linhas: list[list]) -> dict:
    """Salva um relatório novo no histórico. Se outra chamada concorrente já
    tiver salvo o mesmo SQL entre a busca e este insert, devolve o documento
    já existente em vez de duplicar (o índice único em hash_sql garante isso).
    Por padrão, o relatório expira e é apagado automaticamente após
    TEMPO_EXPIRACAO — a menos que seja fixado (veja `fixar`)."""
    documento = {
        "hash_sql": hash_sql(sql_validado),
        "sql": sql_validado,
        "titulo": titulo,
        "colunas": colunas,
        "linhas": linhas,
        "total_linhas": len(linhas),
        "criado_em": datetime.now(timezone.utc),
        "fixado": False,
        "expira_em": datetime.now(timezone.utc) + TEMPO_EXPIRACAO,
    }
    try:
        resultado = get_colecao_historico().insert_one(documento)
        documento["_id"] = resultado.inserted_id
        return documento
    except DuplicateKeyError:
        existente = buscar_por_sql(sql_validado)
        if existente is not None:
            return existente
        raise


def listar() -> list[dict]:
    """Lista os relatórios salvos, do mais recente para o mais antigo, sem os
    dados completos das linhas (usado pela tela de histórico)."""
    cursor = get_colecao_historico().find({}, {"linhas": 0}).sort("criado_em", -1)
    return list(cursor)


def obter(id_relatorio: str) -> dict | None:
    try:
        oid = ObjectId(id_relatorio)
    except InvalidId:
        return None
    return get_colecao_historico().find_one({"_id": oid})


def deletar(id_relatorio: str) -> bool:
    try:
        oid = ObjectId(id_relatorio)
    except InvalidId:
        return False
    resultado = get_colecao_historico().delete_one({"_id": oid})
    return resultado.deleted_count > 0


def fixar(id_relatorio: str) -> bool:
    """Fixa um relatório: ele deixa de expirar (remove o campo `expira_em`,
    que é o que o índice TTL do Mongo usa para apagar automaticamente)."""
    try:
        oid = ObjectId(id_relatorio)
    except InvalidId:
        return False
    resultado = get_colecao_historico().update_one(
        {"_id": oid}, {"$set": {"fixado": True}, "$unset": {"expira_em": ""}}
    )
    return resultado.matched_count > 0


def desfixar(id_relatorio: str) -> bool:
    """Desfixa um relatório: ele volta a expirar, com um novo prazo de
    TEMPO_EXPIRACAO a partir de agora."""
    try:
        oid = ObjectId(id_relatorio)
    except InvalidId:
        return False
    resultado = get_colecao_historico().update_one(
        {"_id": oid},
        {"$set": {"fixado": False, "expira_em": datetime.now(timezone.utc) + TEMPO_EXPIRACAO}},
    )
    return resultado.matched_count > 0
