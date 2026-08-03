"""Rota agregadora de auditoria de dados — roda sob demanda (nunca em
background), só quando o usuário clica no botão do sidebar. Junta achados de
todos os módulos que o usuário logado tem acesso; hoje só existe o provedor
do Financeiro, mas `_PROVEDORES_POR_MODULO` é o ponto de extensão pra quando
outro módulo (Estoque, ...) ganhar backend de verdade — a análise genérica
(`agent/auditoria/analise.py`) nunca importa nada de um módulo específico, só
esta rota conhece os dois lados."""

from ollama import AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.auditoria.analise import Achado, analisar_perfis
from agente_oracle.agent.financeiro.auditoria import construir_perfis_financeiro
from agente_oracle.config import settings
from agente_oracle.server.auth.dependencia import exigir_usuario
from agente_oracle.server.cors import CORS_HEADERS, resposta_preflight
from agente_oracle.tools.auditoria import dispensados
from agente_oracle.tools.auditoria import historico as historico_tools
from agente_oracle.tools.auth import papeis

_PROVEDORES_POR_MODULO = {
    "financeiro": construir_perfis_financeiro,
}


def _achado_para_json(achado: Achado) -> dict:
    return {
        "modulo": achado.modulo,
        "view": achado.view,
        "campo": achado.campo,
        "valor": achado.valor,
        "descricao": achado.descricao,
    }


def registrar(mcp) -> None:
    @mcp.custom_route("/api/auditoria", methods=["GET", "OPTIONS"])
    async def auditoria_route(request: Request) -> Response:
        """Roda a análise de qualidade de dados ao vivo para os módulos que o
        usuário logado tem acesso e devolve os achados que ele ainda não
        dispensou. Cada chamada é uma consulta real ao Ollama — não há cache
        nem job em background por trás."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        modulos_liberados = papeis.modulos_liberados(usuario_ou_erro.get("papeis", []))

        perfis = []
        for modulo in modulos_liberados:
            construir_perfis = _PROVEDORES_POR_MODULO.get(modulo)
            if construir_perfis is not None:
                perfis.extend(construir_perfis())

        ollama_client = AsyncClient(host=settings.ollama_host)
        achados = await analisar_perfis(ollama_client, settings.ollama_model, perfis)

        # Guarda TODO achado fundamentado no histórico (mesmo os que essa
        # pessoa já dispensou antes) — dispensar só afeta o que aparece na
        # tela, não apaga o registro de que aquilo já foi sugerido um dia.
        historico_tools.salvar(usuario_ou_erro["sub"], achados)

        ja_dispensados = dispensados.listar_dispensados(usuario_ou_erro["sub"])
        achados_visiveis = [
            achado
            for achado in achados
            if (achado.modulo, achado.view, achado.campo, achado.valor) not in ja_dispensados
        ]

        return JSONResponse([_achado_para_json(achado) for achado in achados_visiveis], headers=CORS_HEADERS)

    @mcp.custom_route("/api/auditoria/historico", methods=["GET", "OPTIONS"])
    async def auditoria_historico_route(request: Request) -> Response:
        """Lista os achados que a auditoria já encontrou ao longo do tempo
        (todas as execuções, de qualquer usuário), restritos aos módulos que
        quem está consultando tem acesso — nunca expira, ao contrário de
        `/api/relatorios/historico`."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        modulos_liberados = papeis.modulos_liberados(usuario_ou_erro.get("papeis", []))
        registros = historico_tools.listar(modulos_liberados)
        return JSONResponse(registros, headers=CORS_HEADERS)

    @mcp.custom_route("/api/auditoria/dispensar", methods=["POST", "OPTIONS"])
    async def dispensar_route(request: Request) -> Response:
        """Marca um achado como "não é problema" para o usuário logado — ele
        não volta a aparecer nas próximas chamadas de GET /api/auditoria pra
        essa mesma pessoa (a dispensa é por usuário, não global)."""
        if request.method == "OPTIONS":
            return resposta_preflight()

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        corpo = await request.json()
        modulo = str(corpo.get("modulo", "")).strip()
        view = str(corpo.get("view", "")).strip()
        campo = str(corpo.get("campo", "")).strip()
        valor = str(corpo.get("valor", "")).strip()

        if not (modulo and view and campo and valor):
            return JSONResponse(
                {"erro": "Informe modulo, view, campo e valor."}, status_code=400, headers=CORS_HEADERS
            )

        # Revalida o módulo aqui também (não só no GET) — sem isso, um
        # usuário sem acesso a um módulo poderia gravar uma dispensa pra um
        # módulo que nem deveria saber que existe.
        if modulo not in papeis.modulos_liberados(usuario_ou_erro.get("papeis", [])):
            return JSONResponse({"erro": "Acesso restrito a este módulo."}, status_code=403, headers=CORS_HEADERS)

        dispensados.dispensar(usuario_ou_erro["sub"], modulo, view, campo, valor)
        return JSONResponse({"ok": True}, headers=CORS_HEADERS)
