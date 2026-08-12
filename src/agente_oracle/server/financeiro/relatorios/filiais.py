"""Lista as filiais disponíveis (STAGE.EMPRESA) para o usuário escolher antes
de abrir um relatório do Financeiro que dependa de filial (ex: Fluxo de Caixa
Realizado). Compartilhado entre os relatórios do módulo — não é específico
de um relatório só.

Migrado do Oracle transacional do Protheus (SA6010) para o STAGE
(SCIENCE_PROD, ETL/BI) — `STAGE.EMPRESA` é o cadastro de filiais/empresas
desse banco (`CODIGO` bate com a mesma filial de 4 dígitos usada em todo o
resto do módulo, ex: '0101').
"""

from starlette.requests import Request
from starlette.responses import JSONResponse

from agente_oracle.db.connection import get_connection
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_financeiro
from agente_oracle.server.cors import CORS_HEADERS

_QUERY = """
    SELECT TRIM(codigo) AS codigo, identificacao AS nome
    FROM STAGE.empresa
    WHERE excluido = 0
    ORDER BY codigo
"""


def _buscar_filiais() -> list[dict[str, str]]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(_QUERY)
        return [{"codigo": codigo, "nome": nome} for codigo, nome in cursor.fetchall()]


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/filiais", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
    async def listar_filiais_route(request: Request, usuario: dict) -> JSONResponse:
        """Lista as filiais (STAGE.EMPRESA) disponíveis para os relatórios do Financeiro."""
        return JSONResponse(_buscar_filiais(), headers=CORS_HEADERS)
