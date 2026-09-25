"""Checagem de qualidade de chamado de service desk — mesma arquitetura
dos outros agentes do projeto: a IA só recebe o texto do chamado (título,
descrição, categoria) e o histórico da conversa (se já houve alguma
rodada de esclarecimento), e decide se tem informação suficiente pra um
técnico agir; nunca decide sozinha mudar o chamado de status — quem
orquestra isso é `server/ti/chamados.py`, em cima do resultado.

"Suficiente" aqui é julgamento (não um fato verificável contra dado real,
diferente de outros agentes do projeto), então não tem o mesmo tipo de
checagem de fundamentação — a rede de segurança aqui é outra: `usar_ia`
desligado (decisão do time de TI, ver `tools/ti/configuracoes.py`) ou a
IA não devolvendo um julgamento confiável (Ollama fora do ar, resposta
mal formada, ou "insuficiente" sem pergunta de verdade) nunca trava o
chamado nem deixa passar às cegas — cai em `_avaliar_por_regra`, uma
contagem de palavras (do texto ORIGINAL + o que a pessoa já respondeu em
todas as rodadas) que nunca depende de rede. A IA continua sendo a
primeira opção (julgamento semântico bate uma regra de tamanho), a regra
é só o plano B pra quando ela não responde.

Descrição (+ conversa) sem conteúdo real (ex: chamado de teste) também
cai direto na regra, sem passar pela IA: com um modelo local pequeno e
nada pra trabalhar, ela tende a inventar um tema plausível (já visto em
produção) em vez de admitir que não tem base — a regra de palavras é
mais segura nesse caso do que dar à IA algo vazio pra julgar.

`TurnoConversa` é deliberadamente GLPI-agnóstico (não é `tools.ti.glpi.
Followup`) — quem chama (`server/ti/chamados.py`, que já sabe qual é a
conta de serviço da IA) decide o papel de cada mensagem antes de montar a
lista; esse módulo não precisa saber de `Settings`/GLPI pra julgar."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from ollama import AsyncClient

from agente_oracle.agent.core import OPCOES_OLLAMA_PADRAO, resposta_json_como_dict

# Baixado de 15 pra 5 (decisão do Daniel, 2026-09-24, depois de ver o
# texto fixo repetindo em chamados de teste bem curtos) — ainda pega
# descrição praticamente vazia (1-3 palavras), mas deixa relato curto e
# real (ex: "sistema financeiro não abre desde ontem", 6 palavras) chegar
# na IA em vez de cair direto no texto fixo só por causa do tamanho.
_MINIMO_PALAVRAS_DESCRICAO = 5

# Genérica de propósito — cobre chamado de qualquer categoria, não só
# sistema/TI. Mesma mensagem tanto pra descrição sem conteúdo real quanto
# pra falha do Ollama numa descrição igualmente curta (ver `avaliar_chamado`),
# e também pra quando a regra dispara numa rodada além da 1ª (ver docstring
# de `server/ti/chamados.py::processar_chamado_novo` — nesse caso quem
# decide o que fazer com a repetição é quem chama, não este módulo).
_MENSAGEM_DESCRICAO_CURTA = (
    "Pode detalhar melhor o que está acontecendo? Um chamado bem preenchido diz: qual sistema ou "
    "equipamento é afetado; desde quando ou com que frequência; e, o mais importante, COMO o problema "
    'aparece na prática — não só "não funciona" ou "está lento", mas o que acontece de fato (mensagem '
    "de erro? tela congelada? fecha sozinho? fica carregando sem terminar?). Exemplo: \"Não consigo "
    'acessar o sistema de vendas desde ontem à tarde — a tela fica carregando e nunca abre, sem '
    'nenhuma mensagem de erro."'
)

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
    "um chamado recém-aberto — e, se já houver, a conversa de esclarecimento entre você e o "
    "solicitante até agora — e decide se tem informação suficiente pra um técnico RESOLVER o problema "
    "sem precisar voltar e perguntar nada. Considere suficiente só quando os TRÊS pontos abaixo "
    "estiverem cobertos: (1) qual sistema/equipamento é afetado; (2) desde quando ou com que "
    "frequência (quando fizer sentido pra categoria); (3) COMO o problema se manifesta na prática — "
    "um verbo genérico como 'trava', 'não funciona' ou 'está lento' SOZINHO não conta como resposta "
    "pra esse ponto: precisa dizer o que acontece de fato (aparece alguma mensagem de erro? a tela "
    "congela e não reage a nada? o programa fecha sozinho? fica carregando sem nunca terminar?). Sem "
    "esse nível de detalhe, marque `suficiente: false` mesmo já sabendo o sistema e a data — um "
    "chamado só com 'sistema X trava desde ontem' ainda não é o bastante pro técnico agir, só o "
    "bastante pra saber ONDE olhar. Se faltar qualquer um dos três pontos, marque `suficiente: false` "
    "e escreva em `mensagem` uma pergunta curta e direta pedindo especificamente o que falta, baseada "
    "SÓ no que o título, a descrição e a conversa DESSE chamado específico já dizem, e nunca repita "
    "uma pergunta genérica tipo 'detalhe melhor'. Junto da pergunta, inclua um exemplo curto de como "
    "uma descrição completa ficaria PARA ESSE CASO — construído só em cima do que já foi dito (se o "
    "solicitante já citou um sistema, use esse sistema no exemplo; se não citou nenhum, mantenha o "
    "exemplo genérico). Nunca cite um sistema, aplicativo ou equipamento específico (ex: OneDrive, "
    "SAP, Protheus, uma impressora) que não apareça literalmente no título, na descrição ou na "
    "conversa — a categoria pode sugerir um tipo de problema (ex: 'sincronização, acesso'), mas isso "
    "não é licença pra adivinhar qual sistema é; nesse caso pergunte usando os termos genéricos da "
    "própria categoria. Se já existir uma pergunta sua nesta conversa, ANTES de decidir: releia sua "
    "ÚLTIMA pergunta e a resposta mais recente do solicitante, e verifique se essa resposta já cobre o "
    "que você perguntou — MESMO com palavras diferentes das que você sugeriu como exemplo. Exemplo: se "
    "você perguntou 'aparece mensagem de erro, a tela fica em branco, ou os itens desaparecem?' e o "
    "solicitante respondeu 'não vejo mais no menu', isso JÁ RESPONDE o ponto de como o problema se "
    "manifesta — não é uma resposta vaga só porque não usou exatamente uma das suas opções de exemplo; "
    "é uma manifestação específica, só descrita com outras palavras. Se a resposta mais recente cobrir "
    "o que sua última pergunta pedia, considere esse ponto resolvido: marque `suficiente: true` se os "
    "três pontos já estiverem cobertos, ou, se ainda faltar um ponto DIFERENTE, pergunte só sobre esse "
    "outro ponto. Nunca repita a mesma pergunta nem uma pergunta parecida sobre um ponto que a resposta "
    "mais recente já tocou, mesmo que ainda pareça incompleta — nesse caso peça um detalhe A MAIS sobre "
    "o que já foi dito, nunca a mesma pergunta de novo."
)


@dataclass(frozen=True)
class TurnoConversa:
    """Uma mensagem já trocada com o solicitante, numa rodada de
    esclarecimento anterior — `papel="ia"` é uma pergunta que a própria
    triagem automática já fez, `papel="usuario"` é uma resposta da pessoa.
    Quem monta essa lista (`server/ti/chamados.py`) decide o papel de cada
    `Followup` real do GLPI; este módulo só usa o resultado."""

    papel: Literal["ia", "usuario"]
    conteudo: str


@dataclass(frozen=True)
class AvaliacaoChamado:
    suficiente: bool
    mensagem: str
    # De onde veio o julgamento — quem chama usa isso pra decidir se pode
    # confiar que a PRÓXIMA mensagem (se precisar de mais uma rodada) vai
    # ser diferente da anterior: "ia" julga o texto de verdade e varia a
    # cada rodada; "regra" sempre devolve o mesmo texto fixo, então uma
    # rodada extra com origem "regra" repetiria a mensagem anterior.
    origem: Literal["ia", "regra"]


def _avaliar_por_regra(texto: str) -> AvaliacaoChamado:
    """Plano B determinístico — sem IA, sem rede, nunca falha. Só conta
    palavra (do texto ORIGINAL + tudo que já foi respondido, ver
    `avaliar_chamado`): descrição curta demais pra um técnico agir sem
    perguntar nada de volta é o sinal mais barato que dá pra checar sem
    julgamento semântico nenhum."""
    if len(texto.split()) < _MINIMO_PALAVRAS_DESCRICAO:
        return AvaliacaoChamado(suficiente=False, mensagem=_MENSAGEM_DESCRICAO_CURTA, origem="regra")
    return AvaliacaoChamado(suficiente=True, mensagem="", origem="regra")


def _texto_combinado(descricao: str, turnos: Sequence[TurnoConversa]) -> str:
    """Descrição original + só as respostas do USUÁRIO nos turnos — o que
    a IA já perguntou não conta como "conteúdo do chamado" pra decidir se
    há informação suficiente pra julgar (senão a pergunta da própria IA
    infla a contagem de palavras)."""
    respostas_usuario = [turno.conteudo for turno in turnos if turno.papel == "usuario"]
    return "\n".join([descricao, *respostas_usuario])


def _mensagens_para_ia(titulo: str, descricao: str, categoria: str, turnos: Sequence[TurnoConversa]) -> list[dict]:
    mensagens = [
        {"role": "system", "content": _PROMPT_SISTEMA},
        {
            "role": "user",
            "content": f"Título: {titulo}\nCategoria: {categoria}\nDescrição: {descricao}",
        },
    ]
    for turno in turnos:
        mensagens.append({"role": "assistant" if turno.papel == "ia" else "user", "content": turno.conteudo})
    return mensagens


async def avaliar_chamado(
    ollama_client: AsyncClient,
    modelo: str,
    titulo: str,
    descricao: str,
    categoria: str,
    turnos: Sequence[TurnoConversa] = (),
    usar_ia: bool = True,
) -> AvaliacaoChamado:
    """Nunca levanta. `usar_ia=False` pula o Ollama e usa só a regra de
    palavras. Com `usar_ia=True` (padrão), tenta o Ollama primeiro — toda
    vez que a resposta não for um julgamento confiável (erro na chamada,
    JSON mal formado, tipo errado, ou "insuficiente" sem pergunta) cai na
    regra em vez de assumir `suficiente=True` às cegas. Descrição (+
    conversa) sem conteúdo real nem chega a ir pra IA — ver docstring do
    módulo. `turnos` (vazio na 1ª avaliação) é o histórico de
    esclarecimento já trocado — ver `TurnoConversa`."""
    texto_combinado = _texto_combinado(descricao, turnos)
    if not usar_ia or len(texto_combinado.split()) < _MINIMO_PALAVRAS_DESCRICAO:
        return _avaliar_por_regra(texto_combinado)

    try:
        resposta = await ollama_client.chat(
            model=modelo,
            messages=_mensagens_para_ia(titulo, descricao, categoria, turnos),
            format=_SCHEMA,
            options=OPCOES_OLLAMA_PADRAO,
        )
    except Exception:
        return _avaliar_por_regra(texto_combinado)

    corpo = resposta_json_como_dict(resposta.message.content)
    suficiente = corpo.get("suficiente")
    if not isinstance(suficiente, bool):
        return _avaliar_por_regra(texto_combinado)

    mensagem = corpo.get("mensagem")
    mensagem = mensagem.strip() if isinstance(mensagem, str) else ""
    if not suficiente and not mensagem:
        # IA marcou insuficiente mas não disse o que falta — sem uma
        # pergunta de verdade pro usuário, a regra decide melhor que "deixa passar".
        return _avaliar_por_regra(texto_combinado)

    return AvaliacaoChamado(suficiente=suficiente, mensagem=mensagem, origem="ia")
