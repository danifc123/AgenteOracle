"""Cotação USD→R$, só pra CONVERTER exibição de custo — não pra somar
provedores com moeda diferente (isso continua não acontecendo em lugar
nenhum, ver `tools/ia/provedores_llm.py`). Existe porque provedor cobrado
em dólar (ex: OCI) mostra o custo real na moeda que a nota chega, mas
quem decide se compensa trocar de provedor pensa em real — então a tela
mostra os dois.

Busca na AwesomeAPI (pública, sem chave, mantida pela B3/hgbrasil) —
cacheada por `_TTL_SEGUNDOS` pra não bater na API externa a cada `GET
/api/ti/uso-ia` (a tela chama isso a cada 30s agora, ver
`ti-home.ts`/`provedores.ts`). Nunca levanta: falha de rede ou API fora
do ar devolve `None` (ou a última cotação boa em cache, se ainda não
venceu) — quem usa decide o fallback, e o padrão certo é "não converte",
nunca inventar um número."""

import logging
import time
from decimal import Decimal, InvalidOperation

import httpx

_logger = logging.getLogger(__name__)

_URL = "https://economia.awesomeapi.com.br/json/last/USD-BRL"
_TIMEOUT_SEGUNDOS = 5.0
# 1h — cotação de câmbio não precisa ser ao segundo pra decidir "vale a
# pena trocar de provedor", e isso evita bater na API externa a cada
# atualização automática da tela (a cada 30s).
_TTL_SEGUNDOS = 3600

_cache: Decimal | None = None
_cache_expira_em: float = 0.0


def cotacao_usd_brl() -> Decimal | None:
    global _cache, _cache_expira_em
    agora = time.monotonic()
    if _cache is not None and agora < _cache_expira_em:
        return _cache

    try:
        resposta = httpx.get(_URL, timeout=_TIMEOUT_SEGUNDOS)
        resposta.raise_for_status()
        valor = Decimal(resposta.json()["USDBRL"]["bid"])
    except (httpx.HTTPError, KeyError, InvalidOperation, ValueError):
        _logger.exception("Falha buscando cotação USD/BRL")
        return _cache  # cotação antiga (já vencida) é melhor que nenhuma

    _cache = valor
    _cache_expira_em = agora + _TTL_SEGUNDOS
    return _cache
