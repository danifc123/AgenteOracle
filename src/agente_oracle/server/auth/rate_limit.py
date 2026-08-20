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


def _tentativas_na_janela(chave: str, agora: float) -> list[float]:
    tentativas = [instante for instante in _tentativas.get(chave, []) if agora - instante < JANELA_SEGUNDOS]
    _tentativas[chave] = tentativas
    return tentativas


def limpar(chave: str) -> None:
    with _lock:
        _tentativas.pop(chave, None)


def registrar_falha(chave: str) -> None:
    with _lock:
        agora = time.monotonic()
        tentativas = _tentativas_na_janela(chave, agora)
        tentativas.append(agora)


def segundos_ate_liberar(chave: str) -> int | None:
    """`None` se `chave` pode tentar login; senão, quantos segundos faltam até poder de novo."""
    with _lock:
        agora = time.monotonic()
        tentativas = _tentativas_na_janela(chave, agora)
        if len(tentativas) < LIMITE_TENTATIVAS:
            return None
        return max(1, int(JANELA_SEGUNDOS - (agora - min(tentativas))))
