from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import Response

from agente_oracle.config import settings
from agente_oracle.tools.connectivity import check_oracle_connection
from agente_oracle.tools.financeiro import exportar_transacoes_csv, listar_transacoes_financeiras

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


@mcp.custom_route("/api/transacoes/exportar", methods=["GET"])
async def exportar_transacoes_route(request: Request) -> Response:
    """Endpoint HTTP usado pelo frontend para baixar o relatório de transações em CSV."""
    limite = int(request.query_params.get("limite", 20))
    conteudo_csv, nome_arquivo = exportar_transacoes_csv(limite)
    return Response(
        content=conteudo_csv,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{nome_arquivo}"',
            "Access-Control-Allow-Origin": "*",
        },
    )


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
