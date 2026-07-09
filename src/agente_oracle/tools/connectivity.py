from agente_oracle.db.connection import get_connection


def check_oracle_connection() -> str:
    """Testa a conexão com o Oracle e retorna a versão do banco.

    Útil como primeira tool para validar DSN/usuário/senha antes de
    implementar relatórios de negócio.
    """
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT banner FROM v$version WHERE ROWNUM = 1")
        row = cursor.fetchone()
        version = row[0] if row else "desconhecida"
        return f"Conexão OK. Versão do Oracle: {version}"
