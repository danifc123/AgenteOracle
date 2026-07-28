from mcp.server.fastmcp import FastMCP

from agente_oracle.config import settings
from agente_oracle.server import auth, financeiro

mcp = FastMCP("agente-oracle", host=settings.mcp_host, port=settings.mcp_port)

auth.registrar(mcp)
financeiro.registrar(mcp)


def main() -> None:
    import uvicorn
    from starlette.middleware.cors import CORSMiddleware

    # `mcp.run(transport="streamable-http")` monta o app Starlette internamente
    # e já sobe o uvicorn sozinho, sem chance de encaixar middleware — por
    # isso pegamos o app aqui, adicionamos o CORS restrito às origens
    # liberadas (ver `Settings.allowed_origins`) e subimos o uvicorn na mão.
    app = mcp.streamable_http_app()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_methods=["*"],
        allow_headers=["*"],
        # Sem isso o navegador recebe o header `Content-Disposition` (nome do
        # arquivo de download) mas não deixa o JS lê-lo via `fetch`/`XHR` —
        # todo download de Excel (chat, criar relatório, rotinas) caía no
        # nome padrão do frontend em vez do nome real vindo do backend.
        expose_headers=["Content-Disposition"],
    )

    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port, log_level="info")


if __name__ == "__main__":
    main()
