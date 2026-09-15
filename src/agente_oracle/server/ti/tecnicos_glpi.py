"""Suporte ao cadastro de usuário (tela "Usuários", `server/auth/rotas.py`)
— não é sobre chamado, é só a lista de candidatos a vincular como técnico
na hora de criar um login. Arquivo separado de `chamados.py` de propósito,
pra não misturar escopo.

`GET /api/ti/tecnicos-glpi` devolve quem tem o perfil GLPI "Technician"
(`ClienteGLPIReal.buscar_tecnicos_disponiveis`, confirmado ao vivo que
filtra só gente de TI). Protegida com `exigir_administrador` — mesmo nível
de acesso de quem cria usuário (`usuarios_route`), não o módulo "ti" em
geral."""

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.config import settings
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_administrador
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.ti.glpi import criar_cliente


def registrar(mcp) -> None:
    @mcp.custom_route("/api/ti/tecnicos-glpi", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_administrador)
    async def tecnicos_glpi_route(request: Request, usuario: dict) -> Response:
        tecnicos = await criar_cliente(settings).buscar_tecnicos_disponiveis()
        return JSONResponse(
            [{"id": t.id, "nome": t.nome, "titulo": t.titulo} for t in tecnicos],
            headers=CORS_HEADERS,
        )
