from decimal import Decimal, InvalidOperation

from anyio import to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_ti
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.ti import configuracoes as configuracoes_tools

_CASAS_DECIMAIS_MAXIMAS = 3


def _consultar_configuracoes() -> Response:
    return JSONResponse(_corpo_configuracoes(), headers=CORS_HEADERS)


def _corpo_configuracoes() -> dict:
    return {
        "usar_ia_avaliacao_chamado": configuracoes_tools.usar_ia_avaliacao_chamado(),
        "percentual_amostragem_chamados": float(configuracoes_tools.percentual_amostragem_chamados()),
    }


def _definir_configuracoes(corpo: dict) -> Response:
    """Aceita uma ou as duas chaves — quem manda só uma não mexe na outra.
    Valida tudo antes de gravar qualquer coisa, pra um valor inválido não
    deixar a outra configuração gravada pela metade."""
    if "usar_ia_avaliacao_chamado" not in corpo and "percentual_amostragem_chamados" not in corpo:
        return JSONResponse(
            {"erro": "Informe usar_ia_avaliacao_chamado e/ou percentual_amostragem_chamados."},
            status_code=400,
            headers=CORS_HEADERS,
        )

    usar_ia = corpo.get("usar_ia_avaliacao_chamado")
    if "usar_ia_avaliacao_chamado" in corpo and not isinstance(usar_ia, bool):
        return JSONResponse(
            {"erro": "Informe usar_ia_avaliacao_chamado como true/false."},
            status_code=400,
            headers=CORS_HEADERS,
        )

    percentual = None
    if "percentual_amostragem_chamados" in corpo:
        percentual = _percentual_valido(corpo["percentual_amostragem_chamados"])
        if percentual is None:
            return JSONResponse(
                {
                    "erro": "Informe percentual_amostragem_chamados como um número de 0 a 100, "
                    f"com até {_CASAS_DECIMAIS_MAXIMAS} casas decimais."
                },
                status_code=400,
                headers=CORS_HEADERS,
            )

    if "usar_ia_avaliacao_chamado" in corpo:
        configuracoes_tools.definir_usar_ia_avaliacao_chamado(usar_ia)
    if percentual is not None:
        configuracoes_tools.definir_percentual_amostragem_chamados(percentual)
    return JSONResponse(_corpo_configuracoes(), headers=CORS_HEADERS)


def _percentual_valido(bruto) -> Decimal | None:
    """`None` quando não é um número de 0 a 100 com até 3 casas decimais —
    `bool` é rejeitado à parte (em Python `True` é um `int`), e o valor passa
    por `str` antes do `Decimal` pra `33.333` (float do JSON) virar
    exatamente `33.333`, não `33.33299999…`."""
    if isinstance(bruto, bool) or not isinstance(bruto, int | float | str):
        return None
    try:
        valor = Decimal(str(bruto))
    except InvalidOperation:
        return None
    if not valor.is_finite() or valor < 0 or valor > 100:
        return None
    # `normalize()` só pra medir as casas: "33.3330" não tem 4 casas de verdade.
    if valor.normalize().as_tuple().exponent < -_CASAS_DECIMAIS_MAXIMAS:
        return None
    return valor


def registrar(mcp) -> None:
    @mcp.custom_route("/api/ti/configuracoes", methods=["GET", "PUT", "OPTIONS"])
    @rota_protegida("GET, PUT, OPTIONS", exigir=exigir_modulo_ti)
    async def configuracoes_route(request: Request, usuario: dict) -> Response:
        """Expõe `usar_ia_avaliacao_chamado` (ver `agent/ti/qualidade_chamado.py::
        avaliar_chamado`) e `percentual_amostragem_chamados` (ver
        `tools/ti/amostragem_chamados.py`) — ver `tools/ti/configuracoes.py`.
        Só o parsing do corpo (PUT) é assíncrono de verdade; o resto roda em
        thread separada, mesmo padrão de `login_route`."""
        if request.method == "GET":
            return await to_thread.run_sync(_consultar_configuracoes)

        corpo = await request.json()
        return await to_thread.run_sync(_definir_configuracoes, corpo)
