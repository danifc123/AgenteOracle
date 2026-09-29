"""Rotas de "Cores de ambiente" (`tools/auth/cores_ambiente.py`) — autoatendimento
aberto a QUALQUER usuário autenticado (`exigir_usuario`, o padrão de
`rota_protegida` quando `exigir` não é passado — mesmo espírito de
`atualizar_perfil_route`), nunca travado a um módulo: a aparência da tela é
preferência pessoal, não dado de negócio de nenhum módulo específico.

`token` é fechado de propósito (`_TOKENS_VALIDOS`) — só as variáveis CSS que
o frontend realmente sabe aplicar (`servicos/cores-ambiente/cores-ambiente.ts`,
mesma lista duplicada lá; ver docstring de lá pro motivo de não compartilhar
isso entre front/back). Cadastrar cor pra um token fora da lista dá 400 —
sem essa trava, a tabela viraria um key-value genérico sem controle
nenhum sobre o que está sendo guardado."""

from anyio import to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.auth import cores_ambiente as cores_ambiente_tools

_TOKENS_VALIDOS = frozenset(
    {
        "--color-primary",
        "--color-primary-dark",
        "--color-primary-light",
        "--color-bg",
        "--color-surface",
        "--color-border",
        "--color-text",
        "--color-text-muted",
        "--color-accent",
        "--color-accent-dark",
        "--color-primary-soft",
        "--color-primary-softer",
        "--color-error",
        "--color-warning",
        "--color-success",
        # `--color-error-soft`/`--color-warning-soft`/`--color-success-soft`
        # ficam de fora — os dois primeiros são `rgba(...)` com
        # transparência, o `<input type="color">` do frontend só
        # aceita/devolve `#rrggbb` (perderia a transparência); o terceiro
        # fica de fora junto, por consistência, mesmo sendo hex (ver
        # `servicos/cores-ambiente/cores-ambiente.ts`, mesma lista
        # duplicada lá).
    }
)


def _cor_ambiente_detalhe(metodo: str, token: str, usuario_id: int, corpo: dict | None) -> Response:
    if token not in _TOKENS_VALIDOS:
        return JSONResponse({"erro": "Token de cor inválido."}, status_code=400, headers=CORS_HEADERS)
    if metodo == "PUT":
        cor = str((corpo or {}).get("cor") or "").strip()
        if not cor:
            return JSONResponse({"erro": "Informe uma cor."}, status_code=400, headers=CORS_HEADERS)
        resultado = cores_ambiente_tools.definir(usuario_id, token, cor)
        return JSONResponse(resultado, headers=CORS_HEADERS)
    cores_ambiente_tools.remover(usuario_id, token)
    return JSONResponse({"ok": True}, headers=CORS_HEADERS)


def registrar(mcp) -> None:
    @mcp.custom_route("/api/auth/cores-ambiente", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS")
    def cores_ambiente_route(request: Request, usuario: dict) -> Response:
        cores = cores_ambiente_tools.listar(int(usuario["sub"]))
        return JSONResponse(cores, headers=CORS_HEADERS)

    @mcp.custom_route("/api/auth/cores-ambiente/{token}", methods=["PUT", "DELETE", "OPTIONS"])
    @rota_protegida("PUT, DELETE, OPTIONS")
    async def cor_ambiente_detalhe_route(request: Request, usuario: dict) -> Response:
        corpo = await request.json() if request.method == "PUT" else None
        return await to_thread.run_sync(
            _cor_ambiente_detalhe,
            request.method,
            request.path_params["token"],
            int(usuario["sub"]),
            corpo,
        )
