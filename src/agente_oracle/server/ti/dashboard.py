"""Layout de indicadores da Home do TI, personalizável por usuário —
autoatendimento (usa o `usuario` do token, sem `{id}` na URL, mesmo padrão
de `/api/auth/perfil`): cada um só lê/grava o PRÓPRIO layout.

O catálogo/default/gate de desenvolvedor são conhecimento de TI (por isso
moram aqui, não em `tools/auth/layout_dashboard.py`, que só sabe guardar
uma lista JSON qualquer por `usuario_id`+`modulo`, sem saber o que cada
item significa — inclusive a deduplicação por `id` e a normalização de
`tamanho` são feitas aqui, não lá)."""

from typing import Literal, NamedTuple

from anyio import to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_ti
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.auth import layout_dashboard, papeis

_MODULO = "ti"

Tamanho = Literal["pequeno", "grande"]
_TAMANHOS_VALIDOS: set[str] = {"pequeno", "grande"}


class DefinicaoWidget(NamedTuple):
    exige_dev: bool
    tamanho_padrao: Tamanho


# id -> exige o papel `desenvolvedor` pra aparecer (mesma checagem de
# `sessao.ehDesenvolvedor()` no front / `papeis.eh_desenvolvedor()` aqui) +
# tamanho usado quando o item é adicionado sem escolher um, ou quando o
# valor salvo veio inválido (ver `_layout_visivel`).
_CATALOGO: dict[str, DefinicaoWidget] = {
    "chamados_total": DefinicaoWidget(exige_dev=False, tamanho_padrao="pequeno"),
    "chamados_por_status": DefinicaoWidget(exige_dev=False, tamanho_padrao="grande"),
    "ia_tokens_hoje": DefinicaoWidget(exige_dev=True, tamanho_padrao="pequeno"),
    "ia_chamados_avaliados": DefinicaoWidget(exige_dev=True, tamanho_padrao="pequeno"),
    "ia_chamados_escalados": DefinicaoWidget(exige_dev=True, tamanho_padrao="pequeno"),
    "ia_categoria_nao_corrigida": DefinicaoWidget(exige_dev=True, tamanho_padrao="pequeno"),
    # Achados ativos de `historico_seguranca` (login/acesso suspeito no
    # Protheus e no próprio AgenteOracle, ver `agent/ti/deteccao_seguranca.py`)
    # — reaproveita `GET /api/ti/seguranca/historico`, que já devolve só os
    # ativos pra quem não é desenvolvedor; não precisa de rota nova.
    "seguranca_achados_ativos": DefinicaoWidget(exige_dev=False, tamanho_padrao="pequeno"),
}

# Layout de quem nunca personalizou nada — espelha o que a Home mostrava
# fixo antes deste sistema existir, mais o indicador de segurança; um
# não-dev recebe o mesmo default já filtrado pelo gate (ver `_layout_visivel`).
_LAYOUT_PADRAO: list[dict] = [
    {"id": "chamados_total", "tamanho": "pequeno"},
    {"id": "chamados_por_status", "tamanho": "grande"},
    {"id": "ia_tokens_hoje", "tamanho": "pequeno"},
    {"id": "ia_chamados_avaliados", "tamanho": "pequeno"},
    {"id": "ia_chamados_escalados", "tamanho": "pequeno"},
    {"id": "ia_categoria_nao_corrigida", "tamanho": "pequeno"},
    {"id": "seguranca_achados_ativos", "tamanho": "pequeno"},
]


def _layout_visivel(widgets: list[dict], eh_dev: bool) -> list[dict]:
    """Aplica SEMPRE — tanto no GET quanto no PUT (nunca só numa ponta):
    descarta item sem `id` reconhecido no catálogo; descarta id que exige
    `desenvolvedor` pra quem não é (mesmo que a lista já contenha — dado
    legado, ou lista copiada de um dev — o gate vale independente da
    origem); deduplica por `id`, mantendo o 1º visto; normaliza `tamanho`
    pro padrão do catálogo quando ausente ou fora de
    `{"pequeno", "grande"}` (nunca quebra por valor mal formado)."""
    vistos: set[str] = set()
    visiveis: list[dict] = []
    for item in widgets:
        widget_id = item.get("id") if isinstance(item, dict) else None
        definicao = _CATALOGO.get(widget_id) if isinstance(widget_id, str) else None
        if definicao is None or widget_id in vistos or (definicao.exige_dev and not eh_dev):
            continue
        vistos.add(widget_id)
        tamanho = item.get("tamanho")
        if tamanho not in _TAMANHOS_VALIDOS:
            tamanho = definicao.tamanho_padrao
        visiveis.append({"id": widget_id, "tamanho": tamanho})
    return visiveis


def _widgets_para_usuario(usuario: dict) -> list[dict]:
    eh_dev = papeis.eh_desenvolvedor(usuario.get("papeis", []))
    salvo = layout_dashboard.layout_dashboard(int(usuario["sub"]), _MODULO)
    bruto = salvo if salvo is not None else _LAYOUT_PADRAO
    return _layout_visivel(bruto, eh_dev)


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

    # Mesma filtragem do GET, nunca um 400: um id desconhecido/dev-only ou
    # um tamanho inválido chegando aqui (tela desatualizada, ou uso direto
    # da API) é só normalizado/descartado, igual seria na leitura.
    eh_dev = papeis.eh_desenvolvedor(usuario.get("papeis", []))
    filtrados = _layout_visivel(pedidos, eh_dev)
    salvos = layout_dashboard.definir_layout_dashboard(int(usuario["sub"]), _MODULO, filtrados)
    return JSONResponse({"widgets": salvos}, headers=CORS_HEADERS)


def registrar(mcp) -> None:
    @mcp.custom_route("/api/ti/dashboard", methods=["GET", "PUT", "OPTIONS"])
    @rota_protegida("GET, PUT, OPTIONS", exigir=exigir_modulo_ti)
    async def dashboard_route(request: Request, usuario: dict) -> Response:
        """GET lê o layout do usuário logado (nunca falha por falta de linha
        salva, cai no default); PUT substitui a lista inteira."""
        if request.method == "GET":
            return await to_thread.run_sync(_consultar_layout, usuario)

        corpo = await request.json()
        return await to_thread.run_sync(_salvar_layout, usuario, corpo)
