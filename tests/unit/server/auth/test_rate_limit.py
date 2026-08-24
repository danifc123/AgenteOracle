from uuid import uuid4

import pytest

from agente_oracle.server.auth import rate_limit


class _RelogioFalso:
    def __init__(self, inicio: float = 0.0):
        self._agora = inicio

    def avancar(self, segundos: float) -> None:
        self._agora += segundos

    def __call__(self) -> float:
        return self._agora


@pytest.fixture
def relogio(monkeypatch):
    falso = _RelogioFalso()
    monkeypatch.setattr(rate_limit.time, "monotonic", falso)
    return falso


def _chave() -> str:
    return uuid4().hex


def test_chave_nova_nao_esta_bloqueada(relogio):
    assert rate_limit.segundos_ate_liberar(_chave()) is None


def test_cinco_falhas_bloqueiam(relogio):
    chave = _chave()
    for _ in range(rate_limit.LIMITE_TENTATIVAS):
        rate_limit.registrar_falha(chave)

    espera = rate_limit.segundos_ate_liberar(chave)
    assert espera is not None
    assert espera > 0


def test_quatro_falhas_ainda_nao_bloqueiam(relogio):
    chave = _chave()
    for _ in range(rate_limit.LIMITE_TENTATIVAS - 1):
        rate_limit.registrar_falha(chave)

    assert rate_limit.segundos_ate_liberar(chave) is None


def test_bloqueio_expira_apos_a_janela(relogio):
    chave = _chave()
    for _ in range(rate_limit.LIMITE_TENTATIVAS):
        rate_limit.registrar_falha(chave)

    assert rate_limit.segundos_ate_liberar(chave) is not None

    relogio.avancar(rate_limit.JANELA_SEGUNDOS + 1)
    assert rate_limit.segundos_ate_liberar(chave) is None


def test_limpar_libera_na_hora(relogio):
    chave = _chave()
    for _ in range(rate_limit.LIMITE_TENTATIVAS):
        rate_limit.registrar_falha(chave)
    assert rate_limit.segundos_ate_liberar(chave) is not None

    rate_limit.limpar(chave)
    assert rate_limit.segundos_ate_liberar(chave) is None


def test_chaves_diferentes_nao_se_afetam(relogio):
    chave_a = _chave()
    chave_b = _chave()

    for _ in range(rate_limit.LIMITE_TENTATIVAS):
        rate_limit.registrar_falha(chave_a)

    assert rate_limit.segundos_ate_liberar(chave_a) is not None
    assert rate_limit.segundos_ate_liberar(chave_b) is None


def test_limite_customizado_mais_generoso_que_o_padrao(relogio):
    chave = _chave()
    for _ in range(rate_limit.LIMITE_TENTATIVAS):
        rate_limit.registrar_falha(chave, janela_segundos=300)

    # Com o limite padrão (5) já bloquearia, mas um limite customizado maior
    # (ex: chat, mais generoso que login) ainda libera nessa mesma contagem.
    assert rate_limit.segundos_ate_liberar(chave, limite=30, janela_segundos=300) is None


def test_limite_customizado_bloqueia_ao_atingir_o_proprio_teto(relogio):
    chave = _chave()
    for _ in range(30):
        rate_limit.registrar_falha(chave, janela_segundos=300)

    assert rate_limit.segundos_ate_liberar(chave, limite=30, janela_segundos=300) is not None


def test_janela_customizada_expira_independente_da_padrao(relogio):
    chave = _chave()
    for _ in range(30):
        rate_limit.registrar_falha(chave, janela_segundos=60)

    assert rate_limit.segundos_ate_liberar(chave, limite=30, janela_segundos=60) is not None

    relogio.avancar(61)
    assert rate_limit.segundos_ate_liberar(chave, limite=30, janela_segundos=60) is None
