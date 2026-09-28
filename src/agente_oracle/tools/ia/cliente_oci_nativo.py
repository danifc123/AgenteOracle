"""Cliente pro SDK NATIVO da Oracle Cloud Infrastructure (`oci`, pacote
oficial da Oracle) — diferente de `cliente_openai_compativel.py`, que fala
com endpoints compatíveis com a API da OpenAI. Só embedding é suportado
hoje: nenhum modelo de embedding da OCI está disponível pelo endpoint
OpenAI-compatível (confirmado com o suporte Oracle, ticket #1834414) —
`chat` levanta `ChatNaoSuportado` de propósito, pra ficar explícito se
algo tentar usar um provedor assim pra conversa (o cadastro já bloqueia
ativar um provedor só-embedding como provedor de chat do sistema, ver
`server/ti/provedores_llm.py::_ativar`).

Recebe o `oci.generative_ai_inference.GenerativeAiInferenceClient` já
PRONTO (construído por quem chama, com o `Signer` — assinatura RSA, não
bearer token) — mesmo espírito de `ClienteOpenAICompativel` receber um
`AsyncOpenAI` já construído: este arquivo só sabe montar a chamada de
embedding, não a autenticação (isso fica em
`tools/ia/cliente_protegido.py::construir_cliente_llm`, que tem acesso
às credenciais cadastradas)."""

import asyncio

import oci


class ChatNaoSuportado(Exception):
    """Espelha `EmbeddingNaoSuportado` (cliente_openai_compativel.py) —
    esse cliente só fala embedding."""


class ClienteOciNativo:
    def __init__(self, cliente_real, compartment_id: str):
        self._cliente_real = cliente_real
        self._compartment_id = compartment_id

    async def embed(self, *, input, model, **kwargs):
        # SDK da OCI é síncrono (baseado em `requests`) — `asyncio.to_thread`
        # mantém a mesma interface awaitable de `AsyncClient`/`ClienteOpenAICompativel`.
        return await asyncio.to_thread(self._embed_sincrono, input, model)

    def _embed_sincrono(self, input, model: str):
        textos = input if isinstance(input, list) else [input]
        detalhes = oci.generative_ai_inference.models.EmbedTextDetails()
        detalhes.serving_mode = oci.generative_ai_inference.models.OnDemandServingMode(model_id=model)
        detalhes.inputs = textos
        detalhes.truncate = "NONE"
        detalhes.compartment_id = self._compartment_id
        resposta = self._cliente_real.embed_text(detalhes)
        return resposta.data

    async def chat(self, *, messages, **kwargs):
        raise ChatNaoSuportado("Esse provedor (OCI, SDK nativo) só sabe gerar embedding, não responde chat.")
