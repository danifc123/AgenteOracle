from mcp.server.fastmcp import FastMCP

from agente_oracle.config import settings
from agente_oracle.server import financeiro

mcp = FastMCP("agente-oracle", host=settings.mcp_host, port=settings.mcp_port)

financeiro.registrar(mcp)


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
