"""Rota de auditoria de dados — roda sob demanda (nunca em background), só
quando o usuário clica num botão de ação. Escopo por módulo/departamento, de
propósito: cada departamento roda e revisa só a própria auditoria — um
Financeiro nunca dispara nem vê achado de outro módulo.

Cada módulo declara uma lista de `AcaoAuditoria` (`_ACOES_POR_MODULO`) — o
usuário escolhe módulo E ação (`GET /api/auditoria?modulo=X&acao=Y`), nunca
"roda tudo de uma vez": ação tipo `"ia"` gasta uma consulta real ao Ollama
(prompt proporcional a UM departamento, não à soma de todos os que o usuário
tem acesso); ação tipo `"deterministico"` é só SQL, sem custo de IA nenhum,
por isso pode ser rodada solta sem preocupação. `GET /api/auditoria/acoes`
devolve a lista pro frontend montar os botões — dado declarativo, não lista
fixa no Angular, então um módulo novo (ou uma ação nova num módulo existente)
não pede mudança de frontend, só uma entrada nova em `_ACOES_POR_MODULO`."""

from collections.abc import Callable
from dataclasses import dataclass

from anyio import to_thread
from ollama import AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.auditoria.analise import Achado, analisar_perfis, filtrar_valores_conhecidos
from agente_oracle.agent.financeiro.auditoria import (
    construir_achados_desvio_margem,
    construir_perfis_financeiro,
)
from agente_oracle.config import settings
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_desenvolvedor
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.auditoria import dispensados
from agente_oracle.tools.auditoria import historico as historico_tools
from agente_oracle.tools.auth import papeis


@dataclass(frozen=True)
class AcaoAuditoria:
    id: str
    rotulo: str
    descricao: str
    tipo: str  # "ia" (gasta Ollama, devolve list[PerfilCampo]) | "deterministico" (só SQL, devolve list[Achado])
    executar: Callable[[], list]


_ACOES_POR_MODULO: dict[str, list[AcaoAuditoria]] = {
    "financeiro": [
        AcaoAuditoria(
            id="qualidade_dado",
            rotulo="Qualidade de Dado",
            descricao="A IA aponta valores fora do padrão em filial, estado, CPF/CNPJ etc.",
            tipo="ia",
            executar=construir_perfis_financeiro,
        ),
        AcaoAuditoria(
            id="desvio_margem",
            rotulo="Desvio de Margem",
            descricao="Vendas com margem bem abaixo da média do produto nos últimos 30 dias — sem IA.",
            tipo="deterministico",
            executar=construir_achados_desvio_margem,
        ),
    ],
}


def _achado_para_json(achado: Achado) -> dict:
    return {
        "modulo": achado.modulo,
        "view": achado.view,
        "campo": achado.campo,
        "valor": achado.valor,
        "descricao": achado.descricao,
    }


def _auditoria_historico_ativo(corpo: dict) -> Response:
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
        return JSONResponse(
            {"erro": "Achado não encontrado no histórico."}, status_code=404, headers=CORS_HEADERS
        )

    return JSONResponse({"ok": True}, headers=CORS_HEADERS)


def _dispensar(usuario: dict, corpo: dict) -> Response:
    modulo = str(corpo.get("modulo", "")).strip()
    view = str(corpo.get("view", "")).strip()
    campo = str(corpo.get("campo", "")).strip()
    valor = str(corpo.get("valor", "")).strip()

    if not (modulo and view and campo and valor):
        return JSONResponse(
            {"erro": "Informe modulo, view, campo e valor."}, status_code=400, headers=CORS_HEADERS
        )

    # Revalida o módulo aqui também (não só no GET) — sem isso, um usuário
    # sem acesso a um módulo poderia gravar uma dispensa pra um módulo que
    # nem deveria saber que existe.
    if modulo not in papeis.modulos_liberados(usuario.get("papeis", [])):
        return JSONResponse({"erro": "Acesso restrito a este módulo."}, status_code=403, headers=CORS_HEADERS)

    dispensados.dispensar(usuario["sub"], modulo, view, campo, valor)
    historico_tools.definir_ativo(modulo, view, campo, valor, False)
    return JSONResponse({"ok": True}, headers=CORS_HEADERS)


def registrar(mcp) -> None:
    @mcp.custom_route("/api/auditoria/acoes", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS")
    def acoes_auditoria_route(request: Request, usuario: dict) -> Response:
        """Ações de auditoria disponíveis pro módulo informado — o frontend
        monta um botão por ação (`auditoria-painel`), cada uma rodando só a
        própria verificação. Módulo sem ação nenhuma (Estoque/RH/TI hoje)
        devolve lista vazia, não erro — a tela mostra um estado vazio."""
        modulo = request.query_params.get("modulo", "").strip()
        if not modulo or modulo not in papeis.modulos_liberados(usuario.get("papeis", [])):
            return JSONResponse(
                {"erro": "Acesso restrito a este módulo."}, status_code=403, headers=CORS_HEADERS
            )

        acoes = _ACOES_POR_MODULO.get(modulo, [])
        return JSONResponse(
            [
                {"id": acao.id, "rotulo": acao.rotulo, "descricao": acao.descricao, "tipo": acao.tipo}
                for acao in acoes
            ],
            headers=CORS_HEADERS,
        )

    @mcp.custom_route("/api/auditoria/historico/ativo", methods=["PATCH", "OPTIONS"])
    @rota_protegida("PATCH, OPTIONS", exigir=exigir_desenvolvedor)
    async def auditoria_historico_ativo_route(request: Request, usuario: dict) -> Response:
        """Ativa/desativa um achado no histórico (todas as linhas daquela
        tupla `modulo/view/campo/valor` de uma vez) — só pra facilitar
        desenvolvedor testar a auditoria repetidamente: desativado, o achado
        deixa de contar em `ja_identificados` e a próxima execução volta a
        tratá-lo como novo, mesmo sem o dado ter mudado. Restrito ao papel
        `desenvolvedor` (não qualquer administrador). Só o parsing do
        corpo é assíncrono de verdade; o resto roda em thread separada,
        mesmo padrão de `login_route`."""
        corpo = await request.json()
        return await to_thread.run_sync(_auditoria_historico_ativo, corpo)

    @mcp.custom_route("/api/auditoria/historico", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS")
    def auditoria_historico_route(request: Request, usuario: dict) -> Response:
        """Lista os achados que a auditoria já encontrou ao longo do tempo
        (todas as execuções, de qualquer usuário), restritos aos módulos que
        quem está consultando tem acesso — nunca expira, ao contrário de
        `/api/relatorios/historico`. Achado desativado (ver
        `tools/auditoria/historico.definir_ativo`) só aparece pra quem tem o
        papel `desenvolvedor` — pra usuário comum, é como se nunca tivesse
        existido. `?modulo=` é opcional: sem ele, mostra todos os módulos que
        o usuário tem acesso (útil pra quem tem mais de um, ex:
        desenvolvedor); com ele, restringe a um departamento só — mesmo
        filtro que a execução ao vivo em `/api/auditoria`."""
        papeis_usuario = usuario.get("papeis", [])
        modulos_liberados = papeis.modulos_liberados(papeis_usuario)

        modulo = request.query_params.get("modulo", "").strip()
        if modulo:
            if modulo not in modulos_liberados:
                return JSONResponse(
                    {"erro": "Acesso restrito a este módulo."}, status_code=403, headers=CORS_HEADERS
                )
            modulos_liberados = [modulo]

        registros = historico_tools.listar(
            modulos_liberados, incluir_desativados=papeis.eh_desenvolvedor(papeis_usuario)
        )
        return JSONResponse(registros, headers=CORS_HEADERS)

    @mcp.custom_route("/api/auditoria", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS")
    async def auditoria_route(request: Request, usuario: dict) -> Response:
        """Roda UMA ação de auditoria ao vivo (`?modulo=financeiro&acao=
        desvio_margem`) — cada departamento roda e revisa a própria
        auditoria, nunca a de outro, e cada ação só gasta o custo dela
        mesma (`tipo="ia"` chama Ollama; `tipo="deterministico"` é só SQL).
        Devolve TODO achado ATIVO daquele módulo — o quadro completo do que
        está pendente, de qualquer ação já rodada antes, não só o que essa
        execução achou agora. Valor já identificado por QUALQUER execução
        (de qualquer usuário, de qualquer ação) é tirado ANTES de rodar de
        novo (`historico.ja_identificados`), pra não gastar IA
        "redescobrindo" o que já se sabe nem duplicar achado determinístico
        no histórico a cada clique; o que foi excluído assim é buscado de
        volta pronto via `historico.achados_ativos` — chamado ANTES de
        `historico.salvar`, de propósito: `achados_novos` e
        `achados_ja_conhecidos` só ficam disjuntos nessa ordem (lido depois,
        cada achado novo aparecia duplicado — bug real que já aconteceu).
        `ativo` é a ÚNICA fonte de verdade do que aparece aqui — dispensar
        (`/api/auditoria/dispensar`) desativa, então não tem filtro
        adicional por usuário depois disso."""
        modulo = request.query_params.get("modulo", "").strip()
        if not modulo:
            return JSONResponse(
                {"erro": "Informe o módulo a auditar."}, status_code=400, headers=CORS_HEADERS
            )

        if modulo not in papeis.modulos_liberados(usuario.get("papeis", [])):
            return JSONResponse(
                {"erro": "Acesso restrito a este módulo."}, status_code=403, headers=CORS_HEADERS
            )

        acao_id = request.query_params.get("acao", "").strip()
        acao = next((item for item in _ACOES_POR_MODULO.get(modulo, []) if item.id == acao_id), None)
        if acao is None:
            return JSONResponse(
                {"erro": "Informe uma ação de auditoria válida pra esse módulo."},
                status_code=400,
                headers=CORS_HEADERS,
            )

        # Global: um problema já identificado antes (por qualquer execução,
        # de qualquer ação) não é reanalisado nem re-registrado.
        conhecidos = historico_tools.ja_identificados()

        if acao.tipo == "ia":
            perfis = filtrar_valores_conhecidos(acao.executar(), conhecidos)
            ollama_client = AsyncClient(host=settings.ollama_host)
            achados_novos = await analisar_perfis(ollama_client, settings.ollama_model, perfis)
        else:
            achados_novos = [
                achado
                for achado in acao.executar()
                if (achado.modulo, achado.view, achado.campo, achado.valor) not in conhecidos
            ]

        # Busca o que já era conhecido e continua ativo ANTES de salvar os
        # achados novos — nessa ordem, `achados_ja_conhecidos` nunca inclui
        # os que estão em `achados_novos` (são disjuntos de verdade). Buscar
        # DEPOIS de salvar duplicava cada achado novo: um vindo de
        # `achados_novos` (em memória) e o mesmo de novo vindo de
        # `achados_ativos` (lido do banco, já com a linha recém-inserida).
        achados_ja_conhecidos = historico_tools.achados_ativos([modulo])

        # Guarda todo achado novo no histórico (é o que alimenta
        # `ja_identificados` na próxima execução, de qualquer usuário).
        historico_tools.salvar(usuario["sub"], achados_novos)

        # Junta com o que já era conhecido, senão o dialog só mostraria a
        # novidade desta execução — não o que ainda está pendente de
        # execuções anteriores. `achados_ativos` já não traz nada
        # desativado, então não precisa de mais nenhum filtro depois.
        achados = achados_novos + achados_ja_conhecidos

        return JSONResponse([_achado_para_json(achado) for achado in achados], headers=CORS_HEADERS)

    @mcp.custom_route("/api/auditoria/dispensar", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS")
    async def dispensar_route(request: Request, usuario: dict) -> Response:
        """Dispensa um achado — grava o registro por usuário (histórico de
        quem dispensou o quê, em `tools/auditoria/dispensados`) e, além
        disso, DESATIVA o achado globalmente (mesmo mecanismo do botão
        ativar/desativar do desenvolvedor, via `historico.definir_ativo`).
        Isso some da tela de todo mundo (Lista de Auditoria e próximas
        execuções), mas também tira o valor de `ja_identificados` — se o
        dado continuar errado, a IA pode reencontrar e reapontar o mesmo
        problema numa execução futura. "Dispensar" aqui não é "isto nunca é
        um problema", é "parei de olhar pra isso agora". Só o parsing do
        corpo é assíncrono de verdade; o resto roda em thread separada,
        mesmo padrão de `login_route`."""
        corpo = await request.json()
        return await to_thread.run_sync(_dispensar, usuario, corpo)
