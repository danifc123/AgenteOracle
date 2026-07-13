from agente_oracle.config import settings
from agente_oracle.db.connection import get_connection


def check_oracle_connection() -> str:
    """Testa a conexão com o banco configurado (Oracle ou Postgres) e
    retorna a versão do servidor."""
    with get_connection() as connection:
        cursor = connection.cursor()
        if settings.db_backend == "postgres":
            cursor.execute("SELECT version()")
        else:
            cursor.execute("SELECT banner FROM v$version WHERE ROWNUM = 1")
        row = cursor.fetchone()
        version = row[0] if row else "desconhecida"
        return f"Conexão OK. Versão do banco ({settings.db_backend}): {version}"
