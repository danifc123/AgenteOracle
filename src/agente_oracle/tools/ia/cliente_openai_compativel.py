"""Client genérico pra qualquer provedor compatível com a API da OpenAI
(cadastrado por `tools/ia/provedores_llm.py`, ex: OCI Generative AI —
tenancy da própria empresa, liberado pelo suporte Oracle, e-mail do
Gabriel, 04/09/2026) — mesma interface que `ClienteIAProtegido` espera
(`chat`/`embed`), pra `qualidade_chamado.py`/`deteccao_seguranca.py` nem
saberem que trocaram de provedor.

Qual API usar (`estilo_api`) vem de fora, do cadastro — confirmado direto
com o suporte Oracle que isso não é escolha livre do cliente, é o próprio
modelo que exige uma ou outra (ex: `openai.gpt-oss-120b` só fala a
Responses API, os Llama da OCI só falam Chat Completions). Em vez de
adivinhar pelo nome do modelo (frágil pra qualquer provedor que não seja
a OCI), quem cadastra o LLM escolhe o estilo certo na hora — funciona pra
qualquer provedor novo sem precisar editar este arquivo.

`chat` manda `messages` pra Responses API como `input` estruturado — uma
lista de `{"role", "content"}`, igual ao Chat Completions — não como um
texto achatado (`"system: ...\n\nuser: ..."` num blob só). Testado contra
a API real: `input` aceita essa lista igual (`EasyInputMessageParam`,
mesmos papéis `system`/`user`/`assistant` que `messages` já usa). Isso
importa de verdade pra conversa de várias rodadas — um texto achatado
dificulta o modelo distinguir "isso eu perguntei" de "isso ele respondeu"
(bug real, 2026-09-25: chamado de service desk com a mesma pergunta de
esclarecimento repetida, mesmo com o histórico completo — corrigido
trocando o texto achatado pela lista estruturada).

`format` (o JSON schema que todo módulo de IA do projeto já manda —
linguagem do `ollama.AsyncClient.chat(..., format=SCHEMA)`) é traduzido
pro parâmetro de saída estruturada de cada estilo (`text.format` na
Responses API, `response_format` no Chat Completions — nomes diferentes,
mesma ideia) — sem isso, o modelo respondia em texto livre e a gente só
torcia pra vir JSON parseável (bug real: o julgamento de suficiência de
chamado saía mais frouxo com a OCI ativa do que com o Ollama). Sem
`strict: true` de propósito: esse modo da OpenAI exige `additionalProperties:
false` em todo schema, e nenhum schema do projeto declara isso hoje —
ainda restringe a saída ao schema, só não na wire mais rígida da OpenAI."""

from types import SimpleNamespace
from typing import Any, Literal

from openai import AsyncOpenAI

# Nome fixo do schema — a Structured Outputs API exige um `name`, mas
# `format=SCHEMA` (linguagem do Ollama) nunca carrega um; como só existe
# UM schema por chamada, um nome genérico é suficiente.
_NOME_SCHEMA = "resposta_estruturada"

EstiloApi = Literal["chat_completions", "responses"]


class EmbeddingNaoSuportado(Exception):
    """A API compatível com OpenAI não tem endpoint de embedding — a da
    OCI, por exemplo, só tem isso na API nativa dela (confirmado na
    documentação da Oracle). Tipo próprio, não `Exception` genérica, pra
    quem chama (`agent/ti/roteamento_chamado.py`) conseguir distinguir
    "esse provedor não suporta" de qualquer outra falha (rede, provedor
    fora do ar) e avisar o usuário direito, em vez de só cair no fallback
    calado."""


def _kwargs_saida_estruturada_responses(format: dict[str, Any] | None) -> dict[str, Any]:
    """Kwargs extra pra `responses.create` pedir saída em JSON schema
    (estilo Responses API) — `{}` quando ninguém pediu schema (chamada de
    texto livre, sem `format=`), pra não forçar JSON onde não foi pedido."""
    if format is None:
        return {}
    return {"text": {"format": {"type": "json_schema", "name": _NOME_SCHEMA, "schema": format}}}


def _kwargs_saida_estruturada_chat_completions(format: dict[str, Any] | None) -> dict[str, Any]:
    """Mesma ideia de `_kwargs_saida_estruturada_responses`, pro estilo
    Chat Completions — cada estilo usa um parâmetro/formato diferente pra
    pedir a mesma coisa (saída em JSON schema)."""
    if format is None:
        return {}
    return {"response_format": {"type": "json_schema", "json_schema": {"name": _NOME_SCHEMA, "schema": format}}}


class ClienteOpenAICompativel:
    def __init__(self, cliente_real: AsyncOpenAI, estilo_api: EstiloApi = "chat_completions"):
        self._cliente = cliente_real
        self._estilo_api = estilo_api

    async def chat(self, *, model, messages, format: dict[str, Any] | None = None, **_kwargs):
        # `**_kwargs` ainda absorve `options` (`num_ctx` etc — linguagem do
        # Ollama sem equivalente aqui); só `format` é traduzido, ver
        # docstring do módulo.
        if self._estilo_api == "responses":
            resposta = await self._cliente.responses.create(
                model=model, input=messages, **_kwargs_saida_estruturada_responses(format)
            )
            uso = resposta.usage
            detalhes_saida = getattr(uso, "output_tokens_details", None) if uso else None
            return SimpleNamespace(
                message=SimpleNamespace(content=resposta.output_text),
                # Mesmos nomes de atributo do Ollama (`prompt_eval_count`/`eval_count`)
                # de propósito — ver docstring do módulo — `cliente_protegido.py` lê
                # os tokens sem precisar saber qual provedor respondeu.
                prompt_eval_count=uso.input_tokens if uso else None,
                eval_count=uso.output_tokens if uso else None,
                # Só a Responses API expõe isso (confirmado no teste real do
                # suporte Oracle: 31 de 48 tokens de saída foram raciocínio,
                # não resposta) — Chat Completions e Ollama não têm esse
                # conceito, ficam sempre `None`.
                tokens_raciocinio=getattr(detalhes_saida, "reasoning_tokens", None),
            )
        resposta = await self._cliente.chat.completions.create(
            model=model, messages=messages, **_kwargs_saida_estruturada_chat_completions(format)
        )
        uso = resposta.usage
        return SimpleNamespace(
            message=SimpleNamespace(content=resposta.choices[0].message.content),
            prompt_eval_count=uso.prompt_tokens if uso else None,
            eval_count=uso.completion_tokens if uso else None,
        )

    async def embed(self, **_kwargs):
        raise EmbeddingNaoSuportado(
            "Este provedor (endpoint compatível com OpenAI) não tem endpoint de embedding."
        )
