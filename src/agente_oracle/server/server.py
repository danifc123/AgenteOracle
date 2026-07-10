from mcp.server.fastmcp import FastMCP

from agente_oracle.config import settings
from agente_oracle.tools.connectivity import check_oracle_connection
from agente_oracle.tools.financeiro import listar_transacoes_financeiras

mcp = FastMCP("agente-oracle", host=settings.mcp_host, port=settings.mcp_port)


@mcp.tool()
def testar_conexao_oracle() -> str:
    """Testa a conexão com o banco Oracle configurado e retorna a versão do servidor."""
    return check_oracle_connection()


@mcp.tool()
def listar_transacoes(limite: int = 20) -> str:
    """Lista as transações financeiras mais recentes, com dados da conta bancária,
    categoria e fornecedor/cliente vinculados (via INNER JOIN)."""
    return listar_transacoes_financeiras(limite)


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
