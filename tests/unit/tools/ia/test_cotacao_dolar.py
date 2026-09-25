from decimal import Decimal

import httpx
import pytest

from agente_oracle.tools.ia import cotacao_dolar as mod


class _RespostaFake:
    def __init__(self, corpo: dict, levantar: bool = False):
        self._corpo = corpo
        self._levantar = levantar

    def raise_for_status(self) -> None:
        if self._levantar:
            raise httpx.HTTPStatusError("erro", request=None, response=None)  # type: ignore[arg-type]

    def json(self) -> dict:
        return self._corpo


@pytest.fixture(autouse=True)
def _limpar_cache():
    mod._cache = None
    mod._cache_expira_em = 0.0
    yield
    mod._cache = None
    mod._cache_expira_em = 0.0


class TestCotacaoUsdBrl:
    def test_busca_e_devolve_a_cotacao(self, monkeypatch):
        monkeypatch.setattr(
            mod.httpx, "get", lambda *_a, **_kw: _RespostaFake({"USDBRL": {"bid": "5.4321"}})
        )

        assert mod.cotacao_usd_brl() == Decimal("5.4321")

    def test_segunda_chamada_dentro_do_ttl_usa_o_cache_sem_bater_na_api(self, monkeypatch):
        chamadas = []
        monkeypatch.setattr(
            mod.httpx,
            "get",
            lambda *_a, **_kw: (chamadas.append(1), _RespostaFake({"USDBRL": {"bid": "5.0"}}))[1],
        )

        primeira = mod.cotacao_usd_brl()
        segunda = mod.cotacao_usd_brl()

        assert primeira == segunda == Decimal("5.0")
        assert len(chamadas) == 1

    def test_cache_vencido_busca_de_novo(self, monkeypatch):
        chamadas = []
        monkeypatch.setattr(
            mod.httpx,
            "get",
            lambda *_a, **_kw: (chamadas.append(1), _RespostaFake({"USDBRL": {"bid": "5.0"}}))[1],
        )
        mod.cotacao_usd_brl()
        mod._cache_expira_em = 0.0  # simula TTL vencido

        mod.cotacao_usd_brl()

        assert len(chamadas) == 2

    def test_falha_de_rede_sem_cache_devolve_none(self, monkeypatch):
        def _levantar(*_a, **_kw):
            raise httpx.ConnectError("fora do ar")

        monkeypatch.setattr(mod.httpx, "get", _levantar)

        assert mod.cotacao_usd_brl() is None

    def test_falha_de_rede_com_cache_ainda_devolve_a_cotacao_antiga(self, monkeypatch):
        monkeypatch.setattr(
            mod.httpx, "get", lambda *_a, **_kw: _RespostaFake({"USDBRL": {"bid": "5.5"}})
        )
        mod.cotacao_usd_brl()
        mod._cache_expira_em = 0.0  # simula TTL vencido

        def _levantar(*_a, **_kw):
            raise httpx.ConnectError("fora do ar")

        monkeypatch.setattr(mod.httpx, "get", _levantar)

        assert mod.cotacao_usd_brl() == Decimal("5.5")

    def test_resposta_mal_formada_devolve_none(self, monkeypatch):
        monkeypatch.setattr(mod.httpx, "get", lambda *_a, **_kw: _RespostaFake({"algo": "inesperado"}))

        assert mod.cotacao_usd_brl() is None

    def test_status_de_erro_devolve_none(self, monkeypatch):
        monkeypatch.setattr(
            mod.httpx, "get", lambda *_a, **_kw: _RespostaFake({}, levantar=True)
        )

        assert mod.cotacao_usd_brl() is None
