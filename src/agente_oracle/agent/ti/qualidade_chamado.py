"""Checagem de qualidade de chamado de service desk — mesma arquitetura
dos outros agentes do projeto: a IA só recebe o texto do chamado (título,
descrição, categoria) e decide se tem informação suficiente pra um
técnico agir; nunca decide sozinha mudar o chamado de status — quem
orquestra isso é `server/ti/chamados.py`, em cima do resultado.

"Suficiente" aqui é julgamento (não um fato verificável contra dado real,
diferente de outros agentes do projeto), então não tem o mesmo tipo de
checagem de fundamentação — a rede de segurança aqui é outra: `usar_ia`
desligado (decisão do time de TI, ver `tools/ti/configuracoes.py`) ou a
IA não devolvendo um julgamento confiável (Ollama fora do ar, resposta
mal formada, ou "insuficiente" sem pergunta de verdade) nunca trava o
chamado nem deixa passar às cegas — cai em `_avaliar_por_regra`, uma
contagem de palavras da descrição que nunca depende de rede. A IA
continua sendo a primeira opção (julgamento semântico bate uma regra de
tamanho), a regra é só o plano B pra quando ela não responde."""

from dataclasses import dataclass

from ollama import AsyncClient

from agente_oracle.agent.core import OPCOES_OLLAMA_PADRAO, resposta_json_como_dict

_MINIMO_PALAVRAS_DESCRICAO = 15

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


def _avaliar_por_regra(descricao: str) -> AvaliacaoChamado:
    """Plano B determinístico — sem IA, sem rede, nunca falha. Só conta
    palavra: descrição curta demais pra um técnico agir sem perguntar
    nada de volta é o sinal mais barato que dá pra checar sem julgamento
    semântico nenhum."""
    if len(descricao.split()) < _MINIMO_PALAVRAS_DESCRICAO:
        return AvaliacaoChamado(
            suficiente=False,
            mensagem="Pode detalhar melhor o que está acontecendo, qual sistema ou equipamento é afetado, e desde quando?",
        )
    return AvaliacaoChamado(suficiente=True, mensagem="")


async def avaliar_chamado(
    ollama_client: AsyncClient, modelo: str, titulo: str, descricao: str, categoria: str, usar_ia: bool = True
) -> AvaliacaoChamado:
    """Nunca levanta. `usar_ia=False` pula o Ollama e usa só a regra de
    palavras. Com `usar_ia=True` (padrão), tenta o Ollama primeiro — toda
    vez que a resposta não for um julgamento confiável (erro na chamada,
    JSON mal formado, tipo errado, ou "insuficiente" sem pergunta) cai na
    regra em vez de assumir `suficiente=True` às cegas."""
    if not usar_ia:
        return _avaliar_por_regra(descricao)

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
        return _avaliar_por_regra(descricao)

    corpo = resposta_json_como_dict(resposta.message.content)
    suficiente = corpo.get("suficiente")
    if not isinstance(suficiente, bool):
        return _avaliar_por_regra(descricao)

    mensagem = corpo.get("mensagem")
    mensagem = mensagem.strip() if isinstance(mensagem, str) else ""
    if not suficiente and not mensagem:
        # IA marcou insuficiente mas não disse o que falta — sem uma
        # pergunta de verdade pro usuário, a regra decide melhor que "deixa passar".
        return _avaliar_por_regra(descricao)

    return AvaliacaoChamado(suficiente=suficiente, mensagem=mensagem)
