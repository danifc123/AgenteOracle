"""Limite de tentativas de login por usuário — em memória, sem dependência
nova (banco ou lib externa): é suficiente pra um processo único como este
servidor, e evita força bruta de senha no `/api/auth/login`, que antes não
tinha nenhum limite de tentativas.

Bloqueia pelo usuário informado (não pelo IP) — bloquear por IP prende junto
qualquer outra conta usada da mesma rede/máquina.
"""

import threading
import time

LIMITE_TENTATIVAS = 5
JANELA_SEGUNDOS = 3 * 60

_lock = threading.Lock()
_tentativas: dict[str, list[float]] = {}


def _tentativas_na_janela(chave: str, agora: float, janela_segundos: int = JANELA_SEGUNDOS) -> list[float]:
    tentativas = [instante for instante in _tentativas.get(chave, []) if agora - instante < janela_segundos]
    _tentativas[chave] = tentativas
    return tentativas


def limpar(chave: str) -> None:
    with _lock:
        _tentativas.pop(chave, None)


def registrar_falha(chave: str, *, janela_segundos: int = JANELA_SEGUNDOS) -> None:
    with _lock:
        agora = time.monotonic()
        tentativas = _tentativas_na_janela(chave, agora, janela_segundos)
        tentativas.append(agora)


def segundos_ate_liberar(
    chave: str, *, limite: int = LIMITE_TENTATIVAS, janela_segundos: int = JANELA_SEGUNDOS
) -> int | None:
    """`None` se `chave` pode tentar de novo; senão, quantos segundos faltam
    até poder. `limite`/`janela_segundos` permitem um limiar diferente do
    login (ex: chat, mais generoso) sem afetar quem chama sem esses
    argumentos — os defaults preservam o comportamento original."""
    with _lock:
        agora = time.monotonic()
        tentativas = _tentativas_na_janela(chave, agora, janela_segundos)
        if len(tentativas) < limite:
            return None
        return max(1, int(janela_segundos - (agora - min(tentativas))))
