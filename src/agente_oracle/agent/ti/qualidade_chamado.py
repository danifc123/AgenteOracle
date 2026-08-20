"""Checagem de qualidade de chamado de service desk — mesma arquitetura
dos outros agentes do projeto: a IA só recebe o texto do chamado (título,
descrição, categoria) e decide se tem informação suficiente pra um
técnico agir; nunca decide sozinha mudar o chamado de status — quem
orquestra isso é `server/ti/chamados.py`, em cima do resultado.

"Suficiente" aqui é julgamento (não um fato verificável contra dado real,
diferente de outros agentes do projeto), então não tem o mesmo tipo de
checagem de fundamentação — a rede de segurança aqui é outra: falha do
Ollama ou resposta mal formada nunca prende um chamado real "aguardando
usuário" por acidente, sempre libera pra fila nesse caso (best-effort a
favor do usuário, não da IA)."""

from dataclasses import dataclass

from ollama import AsyncClient

from agente_oracle.agent.core import OPCOES_OLLAMA_PADRAO, resposta_json_como_dict

_SCHEMA = {
    "type": "object",
    "properties": {
        "suficiente": {"type": "boolean"},
        "mensagem": {"type": "string"},
    },
    "required": ["suficiente", "mensagem"],
}

_PROMPT_SISTEMA = (
    "Você é um triagista de service desk de TI. Você recebe o título, a descrição e a categoria de "
    "um chamado recém-aberto, e decide se tem informação suficiente pra um técnico começar a "
    "trabalhar nele sem precisar voltar e perguntar nada. Considere suficiente quando dá pra "
    "identificar: o que exatamente está acontecendo (não só 'não funciona' ou 'está lento'), qual "
    "sistema/equipamento é afetado, e (quando fizer sentido pra categoria) desde quando ou com que "
    "frequência. Se faltar isso, marque `suficiente: false` e escreva em `mensagem` uma pergunta "
    "curta, direta e específica pro usuário completar (ex: 'Qual mensagem de erro aparece exatamente, "
    "e em qual sistema?') — nunca genérica tipo 'detalhe melhor'. Se já tiver informação suficiente, "
    "marque `suficiente: true` e deixe `mensagem` vazia."
)


@dataclass(frozen=True)
class AvaliacaoChamado:
    suficiente: bool
    mensagem: str


async def avaliar_chamado(
    ollama_client: AsyncClient, modelo: str, titulo: str, descricao: str, categoria: str
) -> AvaliacaoChamado:
    """Nunca levanta — falha do Ollama ou resposta mal formada é tratada
    como `suficiente=True` (chamado segue pra fila normal), pra IA fora
    do ar nunca travar um chamado real esperando avaliação que não vem."""
    try:
        resposta = await ollama_client.chat(
            model=modelo,
            messages=[
                {"role": "system", "content": _PROMPT_SISTEMA},
                {
                    "role": "user",
                    "content": f"Título: {titulo}\nCategoria: {categoria}\nDescrição: {descricao}",
                },
            ],
            format=_SCHEMA,
            options=OPCOES_OLLAMA_PADRAO,
        )
    except Exception:
        return AvaliacaoChamado(suficiente=True, mensagem="")

    corpo = resposta_json_como_dict(resposta.message.content)
    suficiente = corpo.get("suficiente")
    if not isinstance(suficiente, bool):
        return AvaliacaoChamado(suficiente=True, mensagem="")

    mensagem = corpo.get("mensagem")
    mensagem = mensagem.strip() if isinstance(mensagem, str) else ""
    if not suficiente and not mensagem:
        # IA marcou insuficiente mas não disse o que falta — sem uma
        # pergunta de verdade pro usuário, não vale reter o chamado.
        return AvaliacaoChamado(suficiente=True, mensagem="")

    return AvaliacaoChamado(suficiente=suficiente, mensagem=mensagem)
