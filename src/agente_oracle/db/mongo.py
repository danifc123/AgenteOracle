from functools import lru_cache

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection

from agente_oracle.config import settings

NOME_COLECAO_HISTORICO = "relatorios_historico"


@lru_cache(maxsize=1)
def get_cliente() -> MongoClient:
    cliente = MongoClient(settings.mongo_uri)
    cliente[settings.mongo_db][NOME_COLECAO_HISTORICO].create_index([("hash_sql", ASCENDING)], unique=True)
    return cliente


def get_colecao_historico() -> Collection:
    return get_cliente()[settings.mongo_db][NOME_COLECAO_HISTORICO]
