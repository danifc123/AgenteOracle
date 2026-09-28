"""Home única, personalizável por widget, filtrada pelos papéis do usuário
— autoatendimento (usa `usuario["sub"]`, sem `{id}` na URL, mesmo padrão de
`/api/auth/perfil`). Reaproveita `tools/auth/layout_dashboard.py` (já
genérico por `(usuario_id, modulo)`) chamando com `modulo="home"` — um
módulo VIRTUAL só pra esta tabela, não entra em `papeis.MODULOS_CONHECIDOS`
nem em nenhuma checagem de acesso a módulo real.

Catálogo é a UNIÃO dos catálogos de cada módulo real
(`server/ti/dashboard_widgets.py`, `server/financeiro/dashboard_widgets.py`,
`server/rh/dashboard_widgets.py`) MAIS o catálogo COMUM
(`dashboard_widgets_comuns.py`, sem módulo dono — ex: "Central de suporte"),
com o id de cada widget prefixado pela origem (`"ti:chamados_total"`,
`"financeiro:saldo_projetado"`, `"comum:central_suporte"`) pra nunca colidir
e pra saber contra qual módulo checar acesso (`papeis.tem_acesso_modulo`) —
widget comum não tem módulo pra checar, fica liberado pra qualquer usuário
autenticado (só o `exige_dev`/`exige_administrador` de cada um continua
valendo). Um módulo novo com widget próprio só precisa somar uma entrada em
`_CATALOGOS_POR_MODULO` — nada mais aqui muda.

Todo widget — indicador de dado (`chamados_total`, `saldo_projetado`...) OU
atalho de navegação (`seguranca`, `central_suporte`...) — é a MESMA coisa
pro backend: um id no catálogo, com `exige_dev`/`exige_administrador`/
`tamanho_padrao`. A diferença entre "busca dado" e "só linka pra outra
tela" é só de front (qual componente Angular está por trás do id, ver
`pages/home/catalogo-widgets-home.ts`) — aqui não faz diferença nenhuma.

Começa em BRANCO — diferente do antigo `/api/ti/dashboard` (aposentado em
favor desta rota; ver `server/ti/dashboard_widgets.py`), que caía num
layout fixo quando o usuário nunca personalizava nada. Único default: quem
já tinha personalizado a Home do TI antes desta tela existir
(`layout_dashboard(usuario_id, "ti")`, o bucket antigo) recebe isso migrado
na primeira leitura — não perde o que já montou. Não é gravado de volta
sozinho: só o próximo `PUT` do usuário persiste no bucket novo (`"home"`)."""

from anyio import to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro import dashboard_widgets as financeiro_widgets
from agente_oracle.server.home import dashboard_widgets_comuns as widgets_comuns
from agente_oracle.server.rh import dashboard_widgets as rh_widgets
from agente_oracle.server.ti import dashboard_widgets as ti_widgets
from agente_oracle.tools.auth import layout_dashboard, papeis

_MODULO = "home"
_MODULO_TI_LEGADO = "ti"

# Namespace usado pelo catálogo comum (`dashboard_widgets_comuns.py`) — não
# é um módulo real, não entra em `papeis.MODULOS_CONHECIDOS`; identifica
# pra `_catalogo_unificado` que esses ids não passam por
# `tem_acesso_modulo`.
_NAMESPACE_COMUM = "comum"

# módulo real (dono do widget) -> catálogo desse módulo, sem namespace
# ainda — a chave aqui é sempre um dos `papeis.MODULOS_CONHECIDOS`.
_CATALOGOS_POR_MODULO = {
    "ti": ti_widgets.CATALOGO,
    "financeiro": financeiro_widgets.CATALOGO,
    "rh": rh_widgets.CATALOGO,
}


def _id_namespaced(namespace: str, id_bruto: str) -> str:
    return f"{namespace}:{id_bruto}"


def _catalogo_unificado() -> dict[str, tuple[str | None, object]]:
    """Id namespaced -> (módulo de origem, definição); módulo `None` =
    widget comum, sem módulo dono. Montado a cada chamada; catálogos são
    poucas dezenas de itens no total, sem custo real de recalcular por
    request."""
    unificado: dict[str, tuple[str | None, object]] = {}
    for modulo, catalogo in _CATALOGOS_POR_MODULO.items():
        for id_bruto, definicao in catalogo.items():
            unificado[_id_namespaced(modulo, id_bruto)] = (modulo, definicao)
    for id_bruto, definicao in widgets_comuns.CATALOGO.items():
        unificado[_id_namespaced(_NAMESPACE_COMUM, id_bruto)] = (None, definicao)
    return unificado


def _layout_visivel(widgets: list[dict], papeis_usuario: list[str]) -> list[dict]:
    """Mesmo espírito do antigo `_layout_visivel` do TI, generalizado: o
    gate agora é "tem acesso ao módulo dono deste widget"
    (`tem_acesso_modulo`) — pulado pra widget comum (`modulo is None`) —
    em vez de um único booleano fixo pra rota inteira. `exige_dev` e
    `exige_administrador` de cada item continuam valendo por cima disso.
    Aplica SEMPRE — GET e PUT — nunca só numa ponta."""
    catalogo = _catalogo_unificado()
    eh_dev = papeis.eh_desenvolvedor(papeis_usuario)
    eh_admin = papeis.eh_administrador(papeis_usuario)
    vistos: set[str] = set()
    visiveis: list[dict] = []
    for item in widgets:
        widget_id = item.get("id") if isinstance(item, dict) else None
        entrada = catalogo.get(widget_id) if isinstance(widget_id, str) else None
        if entrada is None or widget_id in vistos:
            continue
        modulo, definicao = entrada
        if modulo is not None and not papeis.tem_acesso_modulo(papeis_usuario, modulo):
            continue
        if definicao.exige_dev and not eh_dev:
            continue
        if definicao.exige_administrador and not eh_admin:
            continue
        vistos.add(widget_id)
        tamanho = item.get("tamanho")
        if tamanho not in ti_widgets.TAMANHOS_VALIDOS:
            tamanho = definicao.tamanho_padrao
        visiveis.append({"id": widget_id, "tamanho": tamanho})
    return visiveis


def _layout_bruto_com_migracao(usuario_id: int) -> list[dict]:
    """`None` salvo em `"home"` cai pro bucket antigo do TI (namespacing
    cada id como `"ti:<id>"`) — só pra quem já tinha personalizado a Home
    do TI antes desta tela existir. Sem nada salvo em nenhum dos dois, a
    Home é realmente vazia (`[]`), não um default fixo."""
    salvo = layout_dashboard.layout_dashboard(usuario_id, _MODULO)
    if salvo is not None:
        return salvo
    layout_ti_antigo = layout_dashboard.layout_dashboard(usuario_id, _MODULO_TI_LEGADO)
    if layout_ti_antigo is None:
        return []
    return [
        {"id": _id_namespaced("ti", item["id"]), "tamanho": item.get("tamanho")}
        for item in layout_ti_antigo
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]


def _widgets_para_usuario(usuario: dict) -> list[dict]:
    bruto = _layout_bruto_com_migracao(int(usuario["sub"]))
    return _layout_visivel(bruto, usuario.get("papeis", []))


def _consultar_layout(usuario: dict) -> Response:
    return JSONResponse({"widgets": _widgets_para_usuario(usuario)}, headers=CORS_HEADERS)


def _formato_valido(pedidos) -> bool:
    return isinstance(pedidos, list) and all(
        isinstance(item, dict) and isinstance(item.get("id"), str) for item in pedidos
    )


def _salvar_layout(usuario: dict, corpo: dict) -> Response:
    pedidos = corpo.get("widgets")
    if not _formato_valido(pedidos):
        return JSONResponse(
            {"erro": "Informe widgets como uma lista de objetos com id."}, status_code=400, headers=CORS_HEADERS
        )

    # Mesma filtragem do GET, nunca um 400: um id desconhecido/sem acesso ou
    # um tamanho inválido chegando aqui é só normalizado/descartado, igual
    # seria na leitura.
    filtrados = _layout_visivel(pedidos, usuario.get("papeis", []))
    salvos = layout_dashboard.definir_layout_dashboard(int(usuario["sub"]), _MODULO, filtrados)
    return JSONResponse({"widgets": salvos}, headers=CORS_HEADERS)


def registrar(mcp) -> None:
    @mcp.custom_route("/api/home/dashboard", methods=["GET", "PUT", "OPTIONS"])
    @rota_protegida("GET, PUT, OPTIONS")
    async def home_dashboard_route(request: Request, usuario: dict) -> Response:
        """GET lê o layout do usuário logado (nunca falha por falta de
        linha salva, cai em `[]` ou no legado do TI migrado); PUT substitui
        a lista inteira. Sem `exigir=` — aberto a qualquer usuário
        autenticado, a visibilidade de cada widget é decidida por item, não
        pela rota inteira."""
        if request.method == "GET":
            return await to_thread.run_sync(_consultar_layout, usuario)

        corpo = await request.json()
        return await to_thread.run_sync(_salvar_layout, usuario, corpo)
