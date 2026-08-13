"""Detecção de possível tentativa de invasão ou acesso suspeito a dado de
cliente — mesma arquitetura do agente de Auditoria de qualidade de dado
(`agent/auditoria/analise.py`): a IA só recebe dado agregado (nunca evento
cru), decide livremente o que parece suspeito, mas todo achado passa por
uma checagem determinística antes de ser devolvido — nunca confiar que um
usuário citado pela IA é real sem conferir contra o dado que foi de fato
mandado pra ela.

Três fontes agregadas viram insumo: login do AgenteOracle (sem IP) e login
do Protheus (com IP/máquina — `agent/ti/perfil_login.py`), mais volume de
acesso a dado exportado (`tools/ti/acessos_dados.py`). Cada achado carrega
`sistema` (`agente_oracle` ou `protheus`) pra deixar claro qual sistema foi
afetado — a resposta a um achado no Protheus é diferente (escala pro time
que administra o Protheus, não só TI interno)."""

import json
from dataclasses import dataclass

from ollama import AsyncClient

from agente_oracle.agent.ti.perfil_login import PerfilLogin, PerfilLoginProtheus
from agente_oracle.tools.ti.acessos_dados import PerfilAcesso

# Mesma constante usada em financeiro.py/analise.py — evita reservar mais
# RAM do que o prompt (perfis agregados) precisa.
_OPCOES_OLLAMA = {"num_ctx": 16384}

_TIPOS_ACHADO = ("tentativa_invasao", "acesso_dados_suspeito")
_SISTEMAS = ("agente_oracle", "protheus")

_ACHADOS_SCHEMA = {
    "type": "object",
    "properties": {
        "achados": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "usuario": {"type": "string"},
                    "sistema": {"type": "string", "enum": list(_SISTEMAS)},
                    "tipo": {"type": "string", "enum": list(_TIPOS_ACHADO)},
                    "descricao": {"type": "string"},
                    "evidencia": {"type": "string"},
                },
                "required": ["usuario", "sistema", "tipo", "descricao", "evidencia"],
            },
        }
    },
    "required": ["achados"],
}

_PROMPT_SISTEMA = (
    "Você é um analista de segurança de TI. Você recebe até três resumos agregados (nunca dado "
    "bruto individual): (1) contagem de eventos de login/bloqueio de conta no sistema "
    "'agente_oracle', (2) login no sistema 'protheus' (com IP e máquina de origem), (3) volume de "
    "acesso/exportação de dado por usuário. Aponte usuário com padrão que pareça tentativa de "
    "invasão (ex: muitas falhas de login, conta bloqueada, ou muitos IPs/máquinas diferentes numa "
    "janela curta) — tipo 'tentativa_invasao' — ou um volume de acesso a dado muito acima do que "
    "parece normal comparado aos demais usuários — tipo 'acesso_dados_suspeito'. Preencha "
    "`sistema` com o sistema de onde veio o dado que embasa o achado ('protheus' só quando "
    "usar o resumo (2)). Não aponte usuário com atividade dentro do padrão comum do grupo só "
    "porque teve alguma falha isolada — poucas falhas de login sozinhas não são motivo. Se nada "
    "parecer fora do padrão, devolva a lista de achados vazia; é o resultado normal na maioria "
    "das execuções. Cite em `usuario` exatamente um dos usuários recebidos, caractere por "
    "caractere — nunca invente. Em `evidencia`, cite os números exatos que embasam o achado (ex: "
    "'5 logins falhos, 1 bloqueio' ou '4 IPs distintos em 7 dias'). Escreva `descricao` em "
    "português, uma frase curta e direta."
)


@dataclass(frozen=True)
class AchadoSeguranca:
    usuario: str
    sistema: str
    tipo: str
    descricao: str
    evidencia: str


async def detectar(
    ollama_client: AsyncClient,
    modelo: str,
    perfis_login: list[PerfilLogin],
    perfis_login_protheus: list[PerfilLoginProtheus],
    perfis_acesso: list[PerfilAcesso],
) -> list[AchadoSeguranca]:
    """Pede à IA que analise os perfis agregados e aponte usuário com
    padrão suspeito. Nunca deixa a chamada quebrar: qualquer falha do
    Ollama, resposta vazia ou mal formada devolve lista vazia — a tela
    simplesmente mostra "nenhum achado" nesse caso."""
    if not perfis_login and not perfis_login_protheus and not perfis_acesso:
        return []

    usuarios_validos = (
        {perfil.usuario for perfil in perfis_login}
        | {perfil.usuario for perfil in perfis_login_protheus}
        | {perfil.usuario_id for perfil in perfis_acesso}
    )

    try:
        resposta = await ollama_client.chat(
            model=modelo,
            messages=[
                {"role": "system", "content": _PROMPT_SISTEMA},
                {
                    "role": "user",
                    "content": _perfis_para_texto(perfis_login, perfis_login_protheus, perfis_acesso),
                },
            ],
            format=_ACHADOS_SCHEMA,
            options=_OPCOES_OLLAMA,
        )
        corpo = json.loads(resposta.message.content or "{}")
    except Exception:
        return []

    achados_brutos = corpo.get("achados")
    if not isinstance(achados_brutos, list):
        return []

    return [
        AchadoSeguranca(
            usuario=achado["usuario"],
            sistema=achado["sistema"],
            tipo=achado["tipo"],
            descricao=achado["descricao"],
            evidencia=achado["evidencia"],
        )
        for achado in achados_brutos
        if _achado_valido(achado) and achado["usuario"] in usuarios_validos
    ]


def _achado_valido(achado: object) -> bool:
    return (
        isinstance(achado, dict)
        and achado.get("sistema") in _SISTEMAS
        and achado.get("tipo") in _TIPOS_ACHADO
        and all(
            isinstance(achado.get(campo), str) and achado.get(campo)
            for campo in ("usuario", "descricao", "evidencia")
        )
    )


def _perfis_para_texto(
    perfis_login: list[PerfilLogin],
    perfis_login_protheus: list[PerfilLoginProtheus],
    perfis_acesso: list[PerfilAcesso],
) -> str:
    blocos = ["EVENTOS DE LOGIN/CONTA NO AGENTE_ORACLE POR USUÁRIO:"]
    for perfil in perfis_login:
        blocos.append(
            f"- {perfil.usuario}: {perfil.login_falha} falhas, {perfil.login_sucesso} sucessos, "
            f"{perfil.conta_bloqueada} bloqueios"
        )

    blocos.append("\nLOGIN NO PROTHEUS POR USUÁRIO (recente):")
    for perfil in perfis_login_protheus:
        blocos.append(
            f"- {perfil.usuario}: {perfil.total_logins} logins, {perfil.ips_distintos} IPs "
            f"distintos, {perfil.maquinas_distintas} máquinas distintas, "
            f"{perfil.tentativas_bloqueio} tentativas de bloqueio, "
            f"{'bloqueado' if perfil.bloqueado else 'não bloqueado'}"
        )

    blocos.append("\nACESSO A DADO POR USUÁRIO (recente):")
    for perfil in perfis_acesso:
        blocos.append(
            f"- {perfil.usuario_id} ({perfil.modulo}/{perfil.recurso}): "
            f"{perfil.total_registros} registros em {perfil.ocorrencias} acessos"
        )

    return "\n".join(blocos)
