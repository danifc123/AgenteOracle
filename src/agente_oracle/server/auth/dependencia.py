"""Checagem de login pras rotas HTTP protegidas — cada `custom_route` que
precisa de usuário logado chama `exigir_usuario(request)` no início e, se o
retorno for um `JSONResponse` (401), devolve isso direto em vez de continuar."""

from starlette.requests import Request
from starlette.responses import JSONResponse

from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.auth import papeis, usuarios
from agente_oracle.tools.auth.token import verificar_token


def exigir_usuario(request: Request) -> dict | JSONResponse:
    cabecalho = request.headers.get("authorization", "")
    if not cabecalho.startswith("Bearer "):
        return JSONResponse({"erro": "Não autenticado."}, status_code=401, headers=CORS_HEADERS)

    payload = verificar_token(cabecalho.removeprefix("Bearer "))
    if payload is None:
        return JSONResponse({"erro": "Sessão expirada ou inválida."}, status_code=401, headers=CORS_HEADERS)

    # Revogação de sessão: o JWT em si não tem como ser invalidado antes de
    # expirar (é sem estado, por design), mas checar aqui o estado atual da
    # conta a cada request faz efeito na prática — desativar ou bloquear
    # alguém corta o acesso já no próximo request, não só em tokens novos.
    if not usuarios.usuario_esta_ativo_e_desbloqueado(int(payload["sub"])):
        return JSONResponse({"erro": "Sessão expirada ou inválida."}, status_code=401, headers=CORS_HEADERS)

    return payload


def exigir_administrador(request: Request) -> dict | JSONResponse:
    """Mesma checagem de `exigir_usuario`, mais a exigência de que o usuário
    tenha um papel administrador (ex: `financeiro_admin`, `desenvolvedor`)."""
    resultado = exigir_usuario(request)
    if isinstance(resultado, JSONResponse):
        return resultado

    if not papeis.eh_administrador(resultado.get("papeis", [])):
        return JSONResponse({"erro": "Acesso restrito a administradores."}, status_code=403, headers=CORS_HEADERS)

    return resultado


def exigir_desenvolvedor(request: Request) -> dict | JSONResponse:
    """Mesma checagem de `exigir_usuario`, mais a exigência do papel
    `desenvolvedor` especificamente (não qualquer administrador) — usada em
    funcionalidades de teste/depuração, como ativar/desativar achado de
    auditoria pra facilitar reproduzir o mesmo cenário várias vezes."""
    resultado = exigir_usuario(request)
    if isinstance(resultado, JSONResponse):
        return resultado

    if not papeis.eh_desenvolvedor(resultado.get("papeis", [])):
        return JSONResponse({"erro": "Acesso restrito a desenvolvedores."}, status_code=403, headers=CORS_HEADERS)

    return resultado


def exigir_modulo_financeiro(request: Request) -> dict | JSONResponse:
    """Mesma checagem de `exigir_usuario`, mais a exigência de que o usuário
    tenha acesso ao módulo financeiro — usada em toda rota `/api/financeiro/*`.
    Sem isso, qualquer conta autenticada
    (independente do papel atribuído) conseguia chamar essas rotas."""
    resultado = exigir_usuario(request)
    if isinstance(resultado, JSONResponse):
        return resultado

    if not papeis.tem_acesso_modulo(resultado.get("papeis", []), "financeiro"):
        return JSONResponse({"erro": "Acesso restrito ao módulo Financeiro."}, status_code=403, headers=CORS_HEADERS)

    return resultado
