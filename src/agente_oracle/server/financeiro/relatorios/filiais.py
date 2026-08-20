"""Lista as filiais disponíveis (STAGE.EMPRESA) para o usuário escolher antes
de abrir um relatório do Financeiro que dependa de filial (ex: Fluxo de Caixa
Realizado). Compartilhado entre os relatórios do módulo — não é específico
de um relatório só.

Migrado do Oracle transacional do Protheus (SA6010) para o STAGE
(SCIENCE_PROD, ETL/BI) — `STAGE.EMPRESA` é o cadastro de filiais/empresas
desse banco (`CODIGO` bate com a mesma filial de 4 dígitos usada em todo o
resto do módulo, ex: '0101').

Filial bloqueada pro usuário logado (`tools/auth/restricoes_filial.py`) nem
aparece nesta lista — não é só a consulta do relatório que fica restrita
(`_comum.py::exigir_filiais_liberadas`), o usuário não deve ter nenhum
indício da existência da filial bloqueada em nenhum componente da tela.
"""

from starlette.requests import Request
from starlette.responses import JSONResponse

from agente_oracle.db.connection import get_connection
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_financeiro
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.auth import restricoes_filial

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


def _filiais_visiveis(filiais: list[dict[str, str]], bloqueadas: set[str]) -> list[dict[str, str]]:
    """Função pura (sem I/O) só pra deixar essa regra testável sem precisar
    de conexão nenhuma — separada de `_buscar_filiais` (que fala com o
    STAGE) de propósito."""
    return [filial for filial in filiais if filial["codigo"] not in bloqueadas]


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/filiais", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
    async def listar_filiais_route(request: Request, usuario: dict) -> JSONResponse:
        """Lista as filiais (STAGE.EMPRESA) disponíveis para os relatórios do
        Financeiro, já excluindo as que o coordenador bloqueou pra esse
        usuário."""
        bloqueadas = restricoes_filial.filiais_bloqueadas(int(usuario["sub"]), "financeiro")
        return JSONResponse(_filiais_visiveis(_buscar_filiais(), bloqueadas), headers=CORS_HEADERS)
