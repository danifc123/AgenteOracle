"""Relatórios/rotinas "fixados" por usuário (Financeiro e Estoque) —
autoatendimento aberto a QUALQUER usuário autenticado (`exigir_usuario`,
o padrão de `rota_protegida` quando `exigir` não é passado — mesmo
espírito de `cores_ambiente.py`), nunca travado a um módulo: é
preferência pessoal de navegação, não dado de negócio de módulo nenhum.

Reaproveita `tools/auth/layout_dashboard.py` (a tabela genérica que a Home
já usa pros widgets — a própria docstring de lá já antecipa esse tipo de
reúso, "RH/Financeiro/Estoque reaproveitam a mesma tabela no futuro sem
migração nova") em vez de criar uma tabela nova: `modulo` aqui é
literalmente a mesma string que já era a chave do localStorage antes
desta rota existir (ex: `"financeiro:cadastros:fixados"`,
`"estoque:especifico-grupo-conceito:fixados"`) — zero renomeação, só
troca de onde mora o dado. De brinde, ganha de graça a limpeza automática
ao apagar usuário (`layout_dashboard.remover_usuario`, já chamado em
`tools/auth/usuarios.py::deletar_usuario`) — diferente de
`relatorio_layouts` (Layouts salvos), que não tem esse hook hoje.

Cada item guardado na lista genérica (`list[dict]`) é só `{"nome": "..."}"`
— a camada de `layout_dashboard` nunca inspeciona o conteúdo, então isso
é só um formato combinado entre esta rota e o frontend, não uma regra
dela. Sem lista de módulos permitidos (diferente de `cores_ambiente`,
onde um token inválido poderia poluir a aparência inteira): aqui é só uma
partição do dado do próprio usuário, travar isso seria validação sem
necessidade real. Sem limite de itens aplicado aqui — o limite de 3 por
tela continua só no frontend, como já era antes desta rota existir."""

from anyio import to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.auth import layout_dashboard


def _nomes_do_layout(itens: list[dict] | None) -> list[str]:
    return [item["nome"] for item in (itens or []) if isinstance(item, dict) and "nome" in item]


def _consultar_fixados(usuario_id: int, modulo: str) -> Response:
    itens = layout_dashboard.layout_dashboard(usuario_id, modulo)
    return JSONResponse({"nomes": _nomes_do_layout(itens)}, headers=CORS_HEADERS)


def _salvar_fixados(usuario_id: int, modulo: str, corpo: dict) -> Response:
    nomes = corpo.get("nomes")
    if not isinstance(nomes, list) or not all(isinstance(nome, str) for nome in nomes):
        return JSONResponse(
            {"erro": "Informe nomes como uma lista de strings."}, status_code=400, headers=CORS_HEADERS
        )
    salvos = layout_dashboard.definir_layout_dashboard(usuario_id, modulo, [{"nome": nome} for nome in nomes])
    return JSONResponse({"nomes": _nomes_do_layout(salvos)}, headers=CORS_HEADERS)


def registrar(mcp) -> None:
    @mcp.custom_route("/api/relatorios-fixados/{modulo}", methods=["GET", "PUT", "OPTIONS"])
    @rota_protegida("GET, PUT, OPTIONS")
    async def relatorios_fixados_route(request: Request, usuario: dict) -> Response:
        """GET lê a lista de fixados do usuário logado pro `modulo` pedido
        (nunca falha por falta de linha salva, cai em `[]`); PUT substitui
        a lista inteira (mesma semântica de `definir_layout_dashboard`)."""
        modulo = request.path_params["modulo"]
        usuario_id = int(usuario["sub"])
        if request.method == "GET":
            return await to_thread.run_sync(_consultar_fixados, usuario_id, modulo)

        corpo = await request.json()
        return await to_thread.run_sync(_salvar_fixados, usuario_id, modulo, corpo)
