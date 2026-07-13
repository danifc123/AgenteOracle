import hashlib
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from agente_oracle.db.mongo import get_colecao_historico


def hash_sql(sql_validado: str) -> str:
    """Normaliza espaços em branco e gera um hash estável do SQL, usado como
    chave de deduplicação (dois SQLs textualmente iguais geram o mesmo hash)."""
    sql_normalizado = " ".join(sql_validado.split())
    return hashlib.sha256(sql_normalizado.encode("utf-8")).hexdigest()


def buscar_por_sql(sql_validado: str) -> dict | None:
    return get_colecao_historico().find_one({"hash_sql": hash_sql(sql_validado)})


def salvar(sql_validado: str, titulo: str, colunas: list[str], linhas: list[list]) -> dict:
    """Salva um relatório novo no histórico. Se outra chamada concorrente já
    tiver salvo o mesmo SQL entre a busca e este insert, devolve o documento
    já existente em vez de duplicar (o índice único em hash_sql garante isso)."""
    documento = {
        "hash_sql": hash_sql(sql_validado),
        "sql": sql_validado,
        "titulo": titulo,
        "colunas": colunas,
        "linhas": linhas,
        "total_linhas": len(linhas),
        "criado_em": datetime.now(timezone.utc),
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


def listar_relatorios_gerados() -> list[dict]:
    """Lista os relatórios que a IA já gerou e estão salvos no histórico —
    título, SQL usado e os dados completos de cada um —, do mais recente
    para o mais antigo.

    Use esta ferramenta ANTES de chamar `executar_consulta_financeira`, para
    checar se já existe um relatório equivalente ao que o usuário está
    pedindo agora (mesmo tema, mesmos filtros/período — mesmo que o SQL fique
    escrito de um jeito um pouco diferente). Se encontrar um equivalente, use
    os `dados` já incluídos aqui para responder ao usuário — NÃO gere um SQL
    novo e NÃO invente valores; os dados já estão nesta resposta.
    """
    return [
        {
            "titulo": documento["titulo"],
            "sql": documento["sql"],
            "gerado_em": documento["criado_em"].isoformat(),
            "dados": [dict(zip(documento["colunas"], linha)) for linha in documento["linhas"]],
        }
        for documento in get_colecao_historico().find().sort("criado_em", -1)
    ]
