"""Decide se um chamado novo entra na amostra analisada pela IA (conta acumulada, `floor`)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal

from agente_oracle.tools.ti import amostragem_repositorio, configuracoes
from agente_oracle.tools.ti.amostragem_repositorio import Decisao, Transacao

_PERCENTUAL_TODOS = Decimal(100)


@dataclass(frozen=True)
class _Regime:
    """Configuração em vigor: percentual, data da última mudança e flag de antigos."""

    percentual: Decimal
    referencia: datetime | None
    ler_antigos: bool


def deve_analisar(chamado_id: int, criado_em: datetime | None = None) -> bool:
    """Decide (e grava) se o chamado entra na amostra; `criado_em=None` nunca é antigo."""
    percentual = configuracoes.percentual_amostragem_chamados()
    if percentual >= _PERCENTUAL_TODOS:
        return True

    regime = _Regime(percentual, configuracoes.percentual_alterado_em(), configuracoes.ler_chamados_antigos())
    antigo = _eh_antigo(criado_em, regime.referencia)
    with amostragem_repositorio.transacao() as transacao:
        anterior = transacao.buscar(chamado_id)
        if anterior is not None and not _deve_reavaliar(anterior, regime, antigo):
            return anterior.amostrado
        if anterior is None and antigo and not regime.ler_antigos:
            return _ignorar(transacao, chamado_id, regime)
        return _decidir(transacao, chamado_id, anterior, regime)


def _decidir(transacao: Transacao, chamado_id: int, anterior: Decisao | None, regime: _Regime) -> bool:
    contados, analisados = transacao.contar(regime.percentual, regime.referencia, regime.ler_antigos)
    ja_contado = anterior is not None and anterior.conta_na_cota
    amostrado = entra_na_amostra(contados - 1 if ja_contado else contados, analisados, regime.percentual)
    decisao = Decisao(amostrado, conta_na_cota=True, regime_desde=regime.referencia)
    transacao.gravar(chamado_id, decisao, regime.percentual, ja_existe=anterior is not None)
    return amostrado


def _deve_reavaliar(anterior: Decisao, regime: _Regime, antigo: bool) -> bool:
    """Só o antigo de fora, com a flag ligada, e uma vez por regime."""
    ja_reavaliado = anterior.conta_na_cota and anterior.regime_desde == regime.referencia
    return antigo and regime.ler_antigos and not anterior.amostrado and not ja_reavaliado


def _eh_antigo(criado_em: datetime | None, referencia: datetime | None) -> bool:
    if criado_em is None or referencia is None:
        return False
    if criado_em.tzinfo is None:
        criado_em = criado_em.replace(tzinfo=UTC)
    return criado_em < referencia


def _ignorar(transacao: Transacao, chamado_id: int, regime: _Regime) -> bool:
    """Antigo nunca visto com a flag desligada: fica de fora sem gastar cota."""
    decisao = Decisao(amostrado=False, conta_na_cota=False, regime_desde=regime.referencia)
    transacao.gravar(chamado_id, decisao, regime.percentual, ja_existe=False)
    return False


def entra_na_amostra(vistos_antes: int, analisados_antes: int, percentual: Decimal) -> bool:
    """O próximo chamado entra quando `floor((vistos_antes + 1) × %)` passa dos já analisados."""
    meta = ((vistos_antes + 1) * percentual / 100).to_integral_value(rounding=ROUND_FLOOR)
    return meta > analisados_antes


def ids_fora_da_amostra() -> set[int]:
    return amostragem_repositorio.ids_fora_da_amostra()
