"""Teto diário de tokens de IA, por departamento — autoatendimento pra
leitura (qualquer usuário do módulo pedido, ver `_DOMINIOS_PERMITIDOS`),
escrita restrita a quem administra ESSE departamento específico
(`papeis.eh_administrador_do_modulo`) ou a `desenvolvedor` (acesso
total). Único lugar do sistema que grava o teto — `tools/ia/cliente_
protegido.py::ClienteIAProtegido._verificar_teto_tokens` é quem de fato
bloqueia uma chamada quando o consumo de hoje (`tools/ia/auditoria_
externa.py::tokens_hoje`) já bateu o teto configurado aqui.

`_DOMINIOS_PERMITIDOS` é só TI e RH — os dois únicos domínios que hoje
passam pelo `ClienteIAProtegido` (Financeiro/Auditoria tocam dado real do
Oracle por um caminho separado, ver docstring de `tools/ia/cliente_
protegido.py`); Estoque não tem chamada de IA nenhuma ainda. Nenhum dos
dois motivos é permanente — quando um desses domínios ganhar chamada de
IA de verdade, basta somar aqui."""

from anyio import to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_usuario
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.auth import papeis
from agente_oracle.tools.ia import auditoria_externa, configuracoes_provedor

_DOMINIOS_PERMITIDOS = ("ti", "rh")


def _teto_valido(bruto) -> bool:
    """Inteiro `>= 0` — `bool` é recusado (é `int` em Python); `0` é
    válido e significa "sem teto" (ver `configuracoes_provedor.teto_tokens_diario`)."""
    return isinstance(bruto, int) and not isinstance(bruto, bool) and bruto >= 0


def _corpo(dominio: str) -> dict:
    return {
        "dominio": dominio,
        "teto_tokens_diario": configuracoes_provedor.teto_tokens_diario(dominio),
        "tokens_hoje": auditoria_externa.tokens_hoje(dominio),
    }


def _consultar(dominio: str) -> Response:
    return JSONResponse(_corpo(dominio), headers=CORS_HEADERS)


def _atualizar(dominio: str, usuario: dict, corpo: dict) -> Response:
    papeis_usuario = usuario.get("papeis", [])
    if not (papeis.eh_desenvolvedor(papeis_usuario) or papeis.eh_administrador_do_modulo(papeis_usuario, dominio)):
        return JSONResponse(
            {"erro": "Só o administrador desse departamento (ou um desenvolvedor) pode alterar o teto."},
            status_code=403,
            headers=CORS_HEADERS,
        )

    teto = corpo.get("teto_tokens_diario")
    if not _teto_valido(teto):
        return JSONResponse(
            {"erro": "Informe teto_tokens_diario como um número inteiro >= 0 (0 = sem teto)."},
            status_code=400,
            headers=CORS_HEADERS,
        )

    configuracoes_provedor.definir_teto_tokens_diario(dominio, teto)
    return JSONResponse(_corpo(dominio), headers=CORS_HEADERS)


def registrar(mcp) -> None:
    @mcp.custom_route("/api/ia/teto-tokens/{dominio}", methods=["GET", "PUT", "OPTIONS"])
    @rota_protegida("GET, PUT, OPTIONS", exigir=exigir_usuario)
    async def teto_tokens_route(request: Request, usuario: dict) -> Response:
        """GET devolve o teto e o consumo de hoje do domínio pedido, pra
        qualquer usuário com acesso a esse módulo. PUT altera o teto — só
        pra quem administra ESSE módulo especificamente, ou desenvolvedor
        (ver docstring do arquivo)."""
        dominio = request.path_params["dominio"]
        if dominio not in _DOMINIOS_PERMITIDOS:
            return Response(status_code=404, headers=CORS_HEADERS)

        if not papeis.tem_acesso_modulo(usuario.get("papeis", []), dominio):
            return JSONResponse(
                {"erro": "Acesso restrito a quem tem esse módulo liberado."},
                status_code=403,
                headers=CORS_HEADERS,
            )

        if request.method == "GET":
            return await to_thread.run_sync(_consultar, dominio)

        corpo = await request.json()
        return await to_thread.run_sync(_atualizar, dominio, usuario, corpo)
