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

`chat` monta o `input` da Responses API concatenando as mensagens num texto
só (papel + conteúdo) — simplificação de propósito, pra não arriscar
inventar um formato de `input` estruturado sem poder testar contra a API
real; se algo se comportar diferente do esperado (ex: saída estruturada por
JSON schema não vier igual ao Ollama), é o primeiro lugar a revisar depois
do teste manual com a chave de verdade."""

from types import SimpleNamespace
from typing import Literal

from openai import AsyncOpenAI

EstiloApi = Literal["chat_completions", "responses"]


class EmbeddingNaoSuportado(Exception):
    """A API compatível com OpenAI não tem endpoint de embedding — a da
    OCI, por exemplo, só tem isso na API nativa dela (confirmado na
    documentação da Oracle). Tipo próprio, não `Exception` genérica, pra
    quem chama (`agent/ti/roteamento_chamado.py`) conseguir distinguir
    "esse provedor não suporta" de qualquer outra falha (rede, provedor
    fora do ar) e avisar o usuário direito, em vez de só cair no fallback
    calado."""


class ClienteOpenAICompativel:
    def __init__(self, cliente_real: AsyncOpenAI, estilo_api: EstiloApi = "chat_completions"):
        self._cliente = cliente_real
        self._estilo_api = estilo_api

    async def chat(self, *, model, messages, **_kwargs):
        # `**_kwargs` absorve `format`/`options` — linguagem do Ollama, que
        # o client protegido manda pra qualquer provedor por baixo.
        if self._estilo_api == "responses":
            entrada = "\n\n".join(f"{mensagem['role']}: {mensagem['content']}" for mensagem in messages)
            resposta = await self._cliente.responses.create(model=model, input=entrada)
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
        resposta = await self._cliente.chat.completions.create(model=model, messages=messages)
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
