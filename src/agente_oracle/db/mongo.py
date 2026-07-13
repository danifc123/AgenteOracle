from functools import lru_cache

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection

from agente_oracle.config import settings

NOME_COLECAO_HISTORICO = "relatorios_historico"


@lru_cache(maxsize=1)
def get_cliente() -> MongoClient:
    cliente = MongoClient(settings.mongo_uri)
    colecao = cliente[settings.mongo_db][NOME_COLECAO_HISTORICO]
    colecao.create_index([("hash_sql", ASCENDING)], unique=True)
    # TTL: o Mongo apaga sozinho o documento quando o relógio passa do valor
    # salvo em expira_em. Documentos fixados não têm esse campo (removido em
    # historico.fixar), então o índice TTL simplesmente os ignora.
    colecao.create_index([("expira_em", ASCENDING)], expireAfterSeconds=0)
    return cliente


def get_colecao_historico() -> Collection:
    return get_cliente()[settings.mongo_db][NOME_COLECAO_HISTORICO]
