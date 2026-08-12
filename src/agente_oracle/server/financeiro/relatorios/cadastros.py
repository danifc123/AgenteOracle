"""Listas de opções vindas de cadastros do banco (clientes, vendedores,
prefixos, tipos, lojas) para os campos de filtro dos relatórios poderem usar
um select com busca — igual ao seletor de filial — em vez de texto livre.
Compartilhado entre os relatórios do módulo, não é específico de um só.

Migrado do Oracle transacional do Protheus (SA1010/SA2010/SA3010/SE1010/
SB1010/SED010/SA6010) para o STAGE (SCIENCE_PROD, ETL/BI) — ver
`db/views/financeiro_science.sql` e o README ("Views curadas do Financeiro")
para o modelo de PESSOA/SOURCETABLE usado nos JOINs abaixo.

ATENÇÃO — "loja" não existe mais como conceito separado: no STAGE, cliente/
fornecedor é identificado só por um código (`PESSOA.CODIGO`) que já parece
embutir a loja (ex: mesmo CNPJ com códigos .../0001, .../0002...). Não há
como listar "as lojas" de forma independente do cliente — `_QUERY_LOJAS`
fica sem fonte de dado até decidirmos o que fazer com o filtro "Loja" nas
telas (hoje usado em Duplicata Mercantil, Posição de Títulos, Retenção de
Impostos e outros — ver `frontend/.../modulos-financeiro.ts`).
"""

from starlette.requests import Request
from starlette.responses import JSONResponse

from agente_oracle.db.connection import get_connection
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_financeiro
from agente_oracle.server.cors import CORS_HEADERS

_QUERY_CLIENTES = """
    SELECT DISTINCT TRIM(c.codigopessoa) AS codigo, p.nome AS nome
    FROM STAGE.cliente c
    JOIN STAGE.pessoa p ON p.codigo = c.codigopessoa AND p.sourcetable = 'SA1010'
    WHERE c.excluido = 0
    ORDER BY nome
"""

_QUERY_FORNECEDORES = """
    SELECT DISTINCT TRIM(f.codigopessoa) AS codigo, p.nome AS nome
    FROM STAGE.fornecedor f
    JOIN STAGE.pessoa p ON p.codigo = f.codigopessoa AND p.sourcetable = 'SA2010'
    WHERE f.excluido = 0
    ORDER BY nome
"""

_QUERY_VENDEDORES = """
    SELECT DISTINCT TRIM(v.codigopessoa) AS codigo, p.nome AS nome
    FROM STAGE.vendedor v
    JOIN STAGE.pessoa p ON p.codigo = v.codigopessoa AND p.sourcetable = 'SA3010'
    WHERE v.excluido = 0
    ORDER BY nome
"""

_QUERY_PREFIXOS = """
    SELECT DISTINCT TRIM(prefixo) AS codigo
    FROM STAGE.contareceber
    WHERE excluido = 0 AND TRIM(prefixo) IS NOT NULL
    ORDER BY codigo
"""

_QUERY_TIPOS = """
    SELECT DISTINCT TRIM(tipo) AS codigo
    FROM STAGE.contareceber
    WHERE excluido = 0 AND TRIM(tipo) IS NOT NULL
    ORDER BY codigo
"""

_QUERY_PRODUTOS = """
    SELECT DISTINCT TRIM(codigo) AS codigo, descricao AS nome
    FROM STAGE.produto
    WHERE excluido = 0
    ORDER BY codigo
"""

_QUERY_NATUREZAS = """
    SELECT DISTINCT TRIM(codigo) AS codigo, descricao AS nome
    FROM STAGE.natureza
    WHERE excluido = 0
    ORDER BY codigo
"""

_QUERY_CONTAS_BANCARIAS = """
    SELECT
        TRIM(sb.codigobanco) || '|' || TRIM(sb.codigoagencia) || '|' || TRIM(sb.codigoconta) AS codigo,
        bb.descricao || ' - ' || TRIM(sb.codigobanco) || '/' || TRIM(sb.codigoagencia) || '/' || TRIM(sb.codigoconta) AS nome
    FROM STAGE.saldobancario sb
    LEFT JOIN STAGE.bancobacen bb ON TO_CHAR(bb.codigo) = LPAD(TRIM(sb.codigobanco), 3, '0')
    WHERE sb.excluido = 0
    ORDER BY nome
"""


def _buscar_com_nome(query: str) -> list[dict[str, str]]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(query)
        return [
            {"codigo": codigo, "nome": f"{codigo} - {nome}" if nome else codigo}
            for codigo, nome in cursor.fetchall()
        ]


def _buscar_pronto(query: str) -> list[dict[str, str]]:
    """Query já devolve codigo/nome formatados (ex: chave composta)."""
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(query)
        return [{"codigo": codigo, "nome": nome} for codigo, nome in cursor.fetchall()]


def _buscar_so_codigo(query: str) -> list[dict[str, str]]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(query)
        return [{"codigo": linha[0], "nome": linha[0]} for linha in cursor.fetchall()]


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/clientes", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
    async def listar_clientes_route(request: Request, usuario: dict) -> JSONResponse:
        """Clientes cadastrados (STAGE.CLIENTE) para o campo de filtro "Cliente"."""
        return JSONResponse(_buscar_com_nome(_QUERY_CLIENTES), headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/contas-bancarias", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
    async def listar_contas_bancarias_route(request: Request, usuario: dict) -> JSONResponse:
        """Contas bancárias cadastradas (STAGE.SALDOBANCARIO) para o campo de filtro "Conta Bancária" — código é "banco|agencia|conta"."""
        return JSONResponse(_buscar_pronto(_QUERY_CONTAS_BANCARIAS), headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/fornecedores", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
    async def listar_fornecedores_route(request: Request, usuario: dict) -> JSONResponse:
        """Fornecedores cadastrados (STAGE.FORNECEDOR) para o campo de filtro "Fornecedor"."""
        return JSONResponse(_buscar_com_nome(_QUERY_FORNECEDORES), headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/lojas", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
    async def listar_lojas_route(request: Request, usuario: dict) -> JSONResponse:
        """Filtro "Loja" — sem fonte de dado no STAGE (ver docstring do módulo):
        devolve sempre vazio até decidirmos o que fazer com esse filtro nas
        telas que ainda o exibem."""
        return JSONResponse([], headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/naturezas", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
    async def listar_naturezas_route(request: Request, usuario: dict) -> JSONResponse:
        """Naturezas financeiras (STAGE.NATUREZA) para os campos de filtro "Natureza De/Até"."""
        return JSONResponse(_buscar_com_nome(_QUERY_NATUREZAS), headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/prefixos", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
    async def listar_prefixos_route(request: Request, usuario: dict) -> JSONResponse:
        """Prefixos de título já usados (STAGE.CONTARECEBER) para o campo de filtro "Prefixo"."""
        return JSONResponse(_buscar_so_codigo(_QUERY_PREFIXOS), headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/produtos", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
    async def listar_produtos_route(request: Request, usuario: dict) -> JSONResponse:
        """Produtos cadastrados (STAGE.PRODUTO) para os campos de filtro "Produto De/Até"."""
        return JSONResponse(_buscar_com_nome(_QUERY_PRODUTOS), headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/tipos", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
    async def listar_tipos_route(request: Request, usuario: dict) -> JSONResponse:
        """Tipos de título já usados (STAGE.CONTARECEBER) para o campo de filtro "Tipo"."""
        return JSONResponse(_buscar_so_codigo(_QUERY_TIPOS), headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/vendedores", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
    async def listar_vendedores_route(request: Request, usuario: dict) -> JSONResponse:
        """Vendedores/consultores cadastrados (STAGE.VENDEDOR) para o campo de filtro "Consultor"."""
        return JSONResponse(_buscar_com_nome(_QUERY_VENDEDORES), headers=CORS_HEADERS)
