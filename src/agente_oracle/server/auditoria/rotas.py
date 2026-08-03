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

from agente_oracle.agent.auditoria.analise import Achado, analisar_perfis, filtrar_valores_conhecidos
from agente_oracle.agent.financeiro.auditoria import construir_perfis_financeiro
from agente_oracle.config import settings
from agente_oracle.server.auth.dependencia import exigir_desenvolvedor, exigir_usuario
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
        usuário logado tem acesso, e devolve TODO achado ATIVO — o quadro
        completo do que está pendente, não só o que apareceu nesta execução.
        Valores já identificados por QUALQUER execução (de qualquer usuário)
        são tirados dos perfis ANTES de chamar a IA (`historico.ja_identificados`
        + `filtrar_valores_conhecidos`), pra não gastar uma chamada de IA
        "redescobrindo" o que já se sabe; os achados assim excluídos da
        análise são buscados de volta prontos, via `historico.achados_ativos`
        (achados_novos e achados_ja_conhecidos são disjuntos por construção:
        o pré-filtro garante que achados_novos nunca repete uma tupla que já
        estava em ja_identificados). `ativo` é a ÚNICA fonte de verdade do
        que aparece aqui — dispensar (`/api/auditoria/dispensar`) desativa,
        então não tem filtro adicional por usuário depois disso; sem isso, um
        achado com `ativo=True` (mostrado como "Ativo" na Lista de Auditoria)
        podia sumir do dialog por causa de uma dispensa antiga, de antes de
        dispensar passar a desativar — bug real que já aconteceu."""
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

        # Global: um problema já identificado antes (por qualquer execução,
        # de qualquer usuário) não é reanalisado — evita gastar uma chamada
        # de IA "redescobrindo" o que já se sabe que existe.
        perfis = filtrar_valores_conhecidos(perfis, historico_tools.ja_identificados())

        ollama_client = AsyncClient(host=settings.ollama_host)
        achados_novos = await analisar_perfis(ollama_client, settings.ollama_model, perfis)

        # Guarda todo achado novo no histórico (é o que alimenta
        # `ja_identificados` na próxima execução, de qualquer usuário).
        historico_tools.salvar(usuario_ou_erro["sub"], achados_novos)

        # Junta com o que já era conhecido e continua ativo, senão o dialog
        # só mostraria a novidade desta execução — não o que ainda está
        # pendente de execuções anteriores. `achados_ativos` já não traz
        # nada desativado, então não precisa de mais nenhum filtro depois.
        achados = achados_novos + historico_tools.achados_ativos(modulos_liberados)

        return JSONResponse([_achado_para_json(achado) for achado in achados], headers=CORS_HEADERS)

    @mcp.custom_route("/api/auditoria/historico", methods=["GET", "OPTIONS"])
    async def auditoria_historico_route(request: Request) -> Response:
        """Lista os achados que a auditoria já encontrou ao longo do tempo
        (todas as execuções, de qualquer usuário), restritos aos módulos que
        quem está consultando tem acesso — nunca expira, ao contrário de
        `/api/relatorios/historico`. Achado desativado (ver
        `tools/auditoria/historico.definir_ativo`) só aparece pra quem tem o
        papel `desenvolvedor` — pra usuário comum, é como se nunca tivesse
        existido."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        papeis_usuario = usuario_ou_erro.get("papeis", [])
        modulos_liberados = papeis.modulos_liberados(papeis_usuario)
        registros = historico_tools.listar(modulos_liberados, incluir_desativados=papeis.eh_desenvolvedor(papeis_usuario))
        return JSONResponse(registros, headers=CORS_HEADERS)

    @mcp.custom_route("/api/auditoria/historico/ativo", methods=["PATCH", "OPTIONS"])
    async def auditoria_historico_ativo_route(request: Request) -> Response:
        """Ativa/desativa um achado no histórico (todas as linhas daquela
        tupla `modulo/view/campo/valor` de uma vez) — só pra facilitar
        desenvolvedor testar a auditoria repetidamente: desativado, o achado
        deixa de contar em `ja_identificados` e a próxima execução volta a
        tratá-lo como novo, mesmo sem o dado ter mudado. Restrito ao papel
        `desenvolvedor` (não qualquer administrador)."""
        if request.method == "OPTIONS":
            return resposta_preflight("PATCH, OPTIONS")

        usuario_ou_erro = exigir_desenvolvedor(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        corpo = await request.json()
        modulo = str(corpo.get("modulo", "")).strip()
        view = str(corpo.get("view", "")).strip()
        campo = str(corpo.get("campo", "")).strip()
        valor = str(corpo.get("valor", "")).strip()
        ativo = corpo.get("ativo")

        if not (modulo and view and campo and valor) or not isinstance(ativo, bool):
            return JSONResponse(
                {"erro": "Informe modulo, view, campo, valor e ativo (booleano)."},
                status_code=400,
                headers=CORS_HEADERS,
            )

        atualizado = historico_tools.definir_ativo(modulo, view, campo, valor, ativo)
        if not atualizado:
            return JSONResponse({"erro": "Achado não encontrado no histórico."}, status_code=404, headers=CORS_HEADERS)

        return JSONResponse({"ok": True}, headers=CORS_HEADERS)

    @mcp.custom_route("/api/auditoria/dispensar", methods=["POST", "OPTIONS"])
    async def dispensar_route(request: Request) -> Response:
        """Dispensa um achado — grava o registro por usuário (histórico de
        quem dispensou o quê, em `tools/auditoria/dispensados`) e, além
        disso, DESATIVA o achado globalmente (mesmo mecanismo do botão
        ativar/desativar do desenvolvedor, via `historico.definir_ativo`).
        Isso some da tela de todo mundo (Lista de Auditoria e próximas
        execuções), mas também tira o valor de `ja_identificados` — se o
        dado continuar errado, a IA pode reencontrar e reapontar o mesmo
        problema numa execução futura. "Dispensar" aqui não é "isto nunca é
        um problema", é "parei de olhar pra isso agora"."""
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
        historico_tools.definir_ativo(modulo, view, campo, valor, False)
        return JSONResponse({"ok": True}, headers=CORS_HEADERS)
