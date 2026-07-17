"""Listas de opções vindas de cadastros do banco (clientes, vendedores,
prefixos, tipos, lojas) para os campos de filtro dos relatórios poderem usar
um select com busca — igual ao seletor de filial — em vez de texto livre.
Compartilhado entre os relatórios do módulo, não é específico de um só.
"""

from starlette.requests import Request
from starlette.responses import JSONResponse

from agente_oracle.db.connection import get_connection
from agente_oracle.server.cors import CORS_HEADERS

_QUERY_CLIENTES = """
    SELECT DISTINCT TRIM(a1_cod) AS codigo, TRIM(a1_nome) AS nome
    FROM sa1010
    WHERE COALESCE(d_e_l_e_t_, ' ') = ' '
    ORDER BY nome
"""

_QUERY_LOJAS = """
    SELECT DISTINCT TRIM(a1_loja) AS codigo
    FROM sa1010
    WHERE COALESCE(d_e_l_e_t_, ' ') = ' '
    ORDER BY codigo
"""

_QUERY_VENDEDORES = """
    SELECT DISTINCT TRIM(a3_cod) AS codigo, TRIM(a3_nome) AS nome
    FROM sa3
    WHERE COALESCE(d_e_l_e_t_, ' ') = ' '
    ORDER BY nome
"""

_QUERY_PREFIXOS = """
    SELECT DISTINCT TRIM(e1_prefixo) AS codigo
    FROM se1010
    WHERE COALESCE(d_e_l_e_t_, ' ') = ' ' AND TRIM(e1_prefixo) <> ''
    ORDER BY codigo
"""

_QUERY_TIPOS = """
    SELECT DISTINCT TRIM(e1_tipo) AS codigo
    FROM se1010
    WHERE COALESCE(d_e_l_e_t_, ' ') = ' ' AND TRIM(e1_tipo) <> ''
    ORDER BY codigo
"""

_QUERY_PRODUTOS = """
    SELECT DISTINCT TRIM(b1_cod) AS codigo, TRIM(b1_desc) AS nome
    FROM sb1010
    WHERE COALESCE(d_e_l_e_t_, ' ') = ' '
    ORDER BY codigo
"""


def _buscar_com_nome(query: str) -> list[dict[str, str]]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(query)
        return [{"codigo": codigo, "nome": f"{codigo} - {nome}" if nome else codigo} for codigo, nome in cursor.fetchall()]


def _buscar_so_codigo(query: str) -> list[dict[str, str]]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(query)
        return [{"codigo": linha[0], "nome": linha[0]} for linha in cursor.fetchall()]


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/clientes", methods=["GET"])
    async def listar_clientes_route(request: Request) -> JSONResponse:
        """Clientes cadastrados (SA1010) para o campo de filtro "Cliente"."""
        return JSONResponse(_buscar_com_nome(_QUERY_CLIENTES), headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/lojas", methods=["GET"])
    async def listar_lojas_route(request: Request) -> JSONResponse:
        """Lojas cadastradas (SA1010) para o campo de filtro "Loja"."""
        return JSONResponse(_buscar_so_codigo(_QUERY_LOJAS), headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/vendedores", methods=["GET"])
    async def listar_vendedores_route(request: Request) -> JSONResponse:
        """Vendedores/consultores cadastrados (SA3) para o campo de filtro "Consultor"."""
        return JSONResponse(_buscar_com_nome(_QUERY_VENDEDORES), headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/prefixos", methods=["GET"])
    async def listar_prefixos_route(request: Request) -> JSONResponse:
        """Prefixos de título já usados (SE1010) para o campo de filtro "Prefixo"."""
        return JSONResponse(_buscar_so_codigo(_QUERY_PREFIXOS), headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/tipos", methods=["GET"])
    async def listar_tipos_route(request: Request) -> JSONResponse:
        """Tipos de título já usados (SE1010) para o campo de filtro "Tipo"."""
        return JSONResponse(_buscar_so_codigo(_QUERY_TIPOS), headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/produtos", methods=["GET"])
    async def listar_produtos_route(request: Request) -> JSONResponse:
        """Produtos cadastrados (SB1010) para os campos de filtro "Produto De/Até"."""
        return JSONResponse(_buscar_com_nome(_QUERY_PRODUTOS), headers=CORS_HEADERS)
