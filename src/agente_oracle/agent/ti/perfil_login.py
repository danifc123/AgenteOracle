"""Perfil agregado de login/conta, por usuário — insumo do agente de
detecção de segurança (`agent/ti/deteccao_seguranca.py`). Nunca manda
evento cru pra IA, só a contagem agregada por usuário, mesmo princípio de
`agent/auditoria/perfil_campo.py`.

Duas fontes independentes, cada uma com seu próprio perfil:
- `perfil_logins`: login do **AgenteOracle** (`tools/auth/eventos_seguranca.py`)
  — sabe QUEM/QUANDO/QUANTAS VEZES, mas não guarda IP nem geolocalização.
- `perfil_logins_protheus`: login do **Protheus**
  (`tools/ti/protheus_login.py`) — banco separado, mas tem IP e máquina de
  origem, o que a fonte acima não tem."""

from dataclasses import dataclass

from agente_oracle.tools.auth import eventos_seguranca
from agente_oracle.tools.ti import protheus_login

_TIPOS_RELEVANTES = ("login_falha", "login_sucesso", "conta_bloqueada")


@dataclass(frozen=True)
class PerfilLogin:
    usuario: str
    login_falha: int
    login_sucesso: int
    conta_bloqueada: int


def perfil_logins(limite: int = 1000) -> list[PerfilLogin]:
    """Agrega os eventos de login/conta mais recentes (`eventos_seguranca.listar`)
    por usuário afetado — só os tipos relevantes pra tentativa de invasão,
    eventos sem usuário afetado (ex: login com usuário inexistente) são
    ignorados aqui."""
    eventos = eventos_seguranca.listar(limite=limite)

    contagens: dict[str, dict[str, int]] = {}
    for evento in eventos:
        tipo = evento["tipo"]
        usuario = evento.get("usuario_afetado")
        if tipo not in _TIPOS_RELEVANTES or not usuario:
            continue
        contagens.setdefault(usuario, dict.fromkeys(_TIPOS_RELEVANTES, 0))[tipo] += 1

    return [
        PerfilLogin(
            usuario=usuario,
            login_falha=valores["login_falha"],
            login_sucesso=valores["login_sucesso"],
            conta_bloqueada=valores["conta_bloqueada"],
        )
        for usuario, valores in contagens.items()
    ]


@dataclass(frozen=True)
class PerfilLoginProtheus:
    usuario: str
    total_logins: int
    ips_distintos: int
    maquinas_distintas: int
    tentativas_bloqueio: int
    bloqueado: bool


def perfil_logins_protheus(dias: int = 7) -> list[PerfilLoginProtheus]:
    """Agrega os logins do Protheus dos últimos `dias` dias por usuário —
    quantidade de IPs e máquinas DISTINTAS é o sinal novo aqui: um usuário
    logando de vários IPs/máquinas diferentes numa janela curta é um
    padrão de invasão que `perfil_logins` (sem IP) nem consegue enxergar.
    Vazio sozinho se `PROTHEUS_DSN` não estiver configurado."""
    logins = protheus_login.logins_recentes(dias)
    bloqueios = {item["usuario"]: item for item in protheus_login.tentativas_bloqueio_recentes()}

    agregados: dict[str, dict] = {}
    for login in logins:
        usuario = login["usuario"]
        info = agregados.setdefault(usuario, {"total": 0, "ips": set(), "maquinas": set()})
        info["total"] += 1
        if login["ip"]:
            info["ips"].add(login["ip"])
        if login["maquina"]:
            info["maquinas"].add(login["maquina"])

    return [
        PerfilLoginProtheus(
            usuario=usuario,
            total_logins=info["total"],
            ips_distintos=len(info["ips"]),
            maquinas_distintas=len(info["maquinas"]),
            tentativas_bloqueio=bloqueios.get(usuario, {}).get("tentativas", 0),
            bloqueado=bloqueios.get(usuario, {}).get("bloqueado", False),
        )
        for usuario, info in agregados.items()
    ]
