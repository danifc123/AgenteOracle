from decimal import Decimal, InvalidOperation

from anyio import to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.config import MODELOS_OCI_GENERATIVE_AI
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_ti
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.auth import papeis
from agente_oracle.tools.ia import configuracoes_provedor
from agente_oracle.tools.ti import configuracoes as configuracoes_tools

_CASAS_DECIMAIS_MAXIMAS = 3
_PROVEDORES_VALIDOS = ("ollama", "oci_openai")

# Só desenvolvedor grava; qualquer usuário do módulo TI lê.
_CHAVES = (
    "usar_ia_avaliacao_chamado",
    "percentual_amostragem_chamados",
    "ler_chamados_antigos",
    "provedor_ia",
    "modelo_ia",
    "teto_tokens_diario",
)


def _corpo_configuracoes() -> dict:
    alterado_em = configuracoes_tools.percentual_alterado_em()
    return {
        "usar_ia_avaliacao_chamado": configuracoes_tools.usar_ia_avaliacao_chamado(),
        "percentual_amostragem_chamados": float(configuracoes_tools.percentual_amostragem_chamados()),
        "percentual_alterado_em": alterado_em.isoformat() if alterado_em else None,
        "ler_chamados_antigos": configuracoes_tools.ler_chamados_antigos(),
        "provedor_ia": configuracoes_provedor.provedor_ia(),
        "modelo_ia": configuracoes_provedor.modelo_ia(),
        "teto_tokens_diario": configuracoes_provedor.teto_tokens_diario(),
    }


def _teto_tokens_valido(bruto) -> bool:
    """Inteiro `>= 0` — `bool` é recusado (é `int` em Python); `0` é válido
    e significa "sem teto" (ver `configuracoes_provedor.teto_tokens_diario`)."""
    return isinstance(bruto, int) and not isinstance(bruto, bool) and bruto >= 0


def _modelo_valido(corpo: dict) -> bool:
    """Texto livre serve pro Ollama (não dá pra saber de antemão quais
    modelos estão baixados/liberados); só é restrito à lista fixa quando o
    provedor EFETIVO (o que vem junto nesse PATCH, ou o que já está
    configurado, se este PATCH não mexer nisso) for a OCI. Vazio sempre é
    válido — significa "usa o padrão do provedor ativo"."""
    modelo = corpo["modelo_ia"]
    if not isinstance(modelo, str):
        return False
    if modelo == "":
        return True
    provedor_efetivo = corpo.get("provedor_ia", configuracoes_provedor.provedor_ia())
    if provedor_efetivo == "oci_openai":
        return modelo in MODELOS_OCI_GENERATIVE_AI
    return True


def _percentual_valido(bruto) -> Decimal | None:
    """Número de 0 a 100 com até 3 casas decimais, ou `None`; `bool` é recusado (é `int` em Python)."""
    if isinstance(bruto, bool) or not isinstance(bruto, int | float | str):
        return None
    try:
        valor = Decimal(str(bruto))  # via str: 33.333 não vira 33.33299…
    except InvalidOperation:
        return None
    if not valor.is_finite() or valor < 0 or valor > 100:
        return None
    if valor.normalize().as_tuple().exponent < -_CASAS_DECIMAIS_MAXIMAS:
        return None
    return valor


def _atualizar_configuracoes(corpo: dict, usuario: dict) -> Response:
    if not any(chave in corpo for chave in _CHAVES):
        return _erro(f"Informe ao menos uma destas chaves: {', '.join(_CHAVES)}.", 400)
    if not papeis.eh_desenvolvedor(usuario.get("papeis", [])):
        return _erro("Acesso restrito a desenvolvedores.", 403)

    mensagem = _validar(corpo)
    if mensagem:
        return _erro(mensagem, 400)

    _gravar(corpo)
    return JSONResponse(_corpo_configuracoes(), headers=CORS_HEADERS)


def _erro(mensagem: str, status_code: int) -> Response:
    return JSONResponse({"erro": mensagem}, status_code=status_code, headers=CORS_HEADERS)


def _gravar(corpo: dict) -> None:
    """Grava só as chaves enviadas; `corpo` já foi validado por `_validar`."""
    if "usar_ia_avaliacao_chamado" in corpo:
        configuracoes_tools.definir_usar_ia_avaliacao_chamado(corpo["usar_ia_avaliacao_chamado"])
    if "ler_chamados_antigos" in corpo:
        configuracoes_tools.definir_ler_chamados_antigos(corpo["ler_chamados_antigos"])
    if "percentual_amostragem_chamados" in corpo:
        configuracoes_tools.definir_percentual_amostragem_chamados(
            _percentual_valido(corpo["percentual_amostragem_chamados"])
        )
    if "provedor_ia" in corpo:
        configuracoes_provedor.definir_provedor_ia(corpo["provedor_ia"])
    if "modelo_ia" in corpo:
        configuracoes_provedor.definir_modelo_ia(corpo["modelo_ia"])
    if "teto_tokens_diario" in corpo:
        configuracoes_provedor.definir_teto_tokens_diario(corpo["teto_tokens_diario"])


def _validar(corpo: dict) -> str | None:
    """Mensagem do primeiro valor inválido, ou `None`; valida tudo antes de gravar qualquer coisa."""
    for chave in ("usar_ia_avaliacao_chamado", "ler_chamados_antigos"):
        if chave in corpo and not isinstance(corpo[chave], bool):
            return f"Informe {chave} como true/false."
    if (
        "percentual_amostragem_chamados" in corpo
        and _percentual_valido(corpo["percentual_amostragem_chamados"]) is None
    ):
        return (
            "Informe percentual_amostragem_chamados como um número de 0 a 100, "
            f"com até {_CASAS_DECIMAIS_MAXIMAS} casas decimais."
        )
    if "provedor_ia" in corpo and corpo["provedor_ia"] not in _PROVEDORES_VALIDOS:
        return f"Informe provedor_ia como um destes: {', '.join(_PROVEDORES_VALIDOS)}."
    if "modelo_ia" in corpo and not _modelo_valido(corpo):
        return (
            f"Informe modelo_ia como um destes pra OCI Generative AI: "
            f"{', '.join(MODELOS_OCI_GENERATIVE_AI)} (ou vazio pra usar o padrão)."
        )
    if "teto_tokens_diario" in corpo and not _teto_tokens_valido(corpo["teto_tokens_diario"]):
        return "Informe teto_tokens_diario como um número inteiro >= 0 (0 = sem teto)."
    return None


def _consultar_configuracoes() -> Response:
    return JSONResponse(_corpo_configuracoes(), headers=CORS_HEADERS)


def registrar(mcp) -> None:
    @mcp.custom_route("/api/ti/configuracoes", methods=["GET", "PATCH", "OPTIONS"])
    @rota_protegida("GET, PATCH, OPTIONS", exigir=exigir_modulo_ti)
    async def configuracoes_route(request: Request, usuario: dict) -> Response:
        """GET lê as configurações; PATCH altera só as chaves enviadas (só desenvolvedor)."""
        if request.method == "GET":
            return await to_thread.run_sync(_consultar_configuracoes)

        corpo = await request.json()
        return await to_thread.run_sync(_atualizar_configuracoes, corpo, usuario)
