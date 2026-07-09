from mcp.server.fastmcp import FastMCP

from agente_oracle.config import settings
from agente_oracle.tools.connectivity import check_oracle_connection

mcp = FastMCP("agente-oracle", host=settings.mcp_host, port=settings.mcp_port)


@mcp.tool()
def testar_conexao_oracle() -> str:
    """Testa a conexão com o banco Oracle configurado e retorna a versão do servidor."""
    return check_oracle_connection()


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
