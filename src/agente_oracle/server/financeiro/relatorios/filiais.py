"""Lista as filiais disponíveis (SA6010) para o usuário escolher antes de
abrir um relatório do Financeiro que dependa de filial (ex: Fluxo de Caixa
Realizado). Compartilhado entre os relatórios do módulo — não é específico
de um relatório só.
"""

from starlette.requests import Request
from starlette.responses import JSONResponse

from agente_oracle.db.connection import get_connection
from agente_oracle.server.auth.dependencia import exigir_usuario
from agente_oracle.server.cors import CORS_HEADERS, resposta_preflight

_QUERY = """
    SELECT DISTINCT a6_filial
    FROM sa6010
    WHERE COALESCE(d_e_l_e_t_, ' ') = ' '
    ORDER BY a6_filial
"""


def _buscar_filiais() -> list[str]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(_QUERY)
        return [linha[0] for linha in cursor.fetchall()]


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/filiais", methods=["GET", "OPTIONS"])
    async def listar_filiais_route(request: Request) -> JSONResponse:
        """Lista as filiais (SA6010) disponíveis para os relatórios do Financeiro."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        filiais = [{"codigo": codigo, "nome": codigo} for codigo in _buscar_filiais()]
        return JSONResponse(filiais, headers=CORS_HEADERS)
