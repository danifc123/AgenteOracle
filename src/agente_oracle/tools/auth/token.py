"""Geração e verificação do token de login (JWT, sem estado no servidor — o
token carrega usuário/nome/papéis assinados e expira sozinho em
`AUTH_TOKEN_HORAS`). Trade-off aceito: não dá pra revogar um usuário na hora
antes do token expirar."""

from datetime import datetime, timedelta, timezone

import jwt

from agente_oracle.config import settings

_ALGORITMO = "HS256"


def gerar_token(usuario_id: int, usuario: str, nome: str, papeis: list[str]) -> str:
    agora = datetime.now(timezone.utc)
    payload = {
        "sub": str(usuario_id),
        "usuario": usuario,
        "nome": nome,
        "papeis": papeis,
        "iat": agora,
        "exp": agora + timedelta(hours=settings.auth_token_horas),
    }
    return jwt.encode(payload, settings.auth_secret_key, algorithm=_ALGORITMO)


def verificar_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.auth_secret_key, algorithms=[_ALGORITMO])
    except jwt.PyJWTError:
        return None
