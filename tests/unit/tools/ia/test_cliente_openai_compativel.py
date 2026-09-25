import pytest

from agente_oracle.tools.ia.cliente_openai_compativel import (
    _NOME_SCHEMA,
    ClienteOpenAICompativel,
    EmbeddingNaoSuportado,
)

_SCHEMA_TESTE = {
    "type": "object",
    "properties": {"suficiente": {"type": "boolean"}},
    "required": ["suficiente"],
}


class _DetalhesSaidaFake:
    def __init__(self, reasoning_tokens: int):
        self.reasoning_tokens = reasoning_tokens


class _UsoResponsesFake:
    def __init__(self, input_tokens: int, output_tokens: int, output_tokens_details: object = None):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.output_tokens_details = output_tokens_details


class _UsoChatCompletionsFake:
    def __init__(self, prompt_tokens: int, completion_tokens: int):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _RespostaResponsesFake:
    def __init__(self, texto: str, uso: _UsoResponsesFake | None):
        self.output_text = texto
        self.usage = uso


class _MensagemChatFake:
    def __init__(self, texto: str):
        self.content = texto


class _EscolhaChatFake:
    def __init__(self, texto: str):
        self.message = _MensagemChatFake(texto)


class _RespostaChatCompletionsFake:
    def __init__(self, texto: str, uso: _UsoChatCompletionsFake | None):
        self.choices = [_EscolhaChatFake(texto)]
        self.usage = uso


class _ResponsesFake:
    def __init__(self, texto: str, uso: _UsoResponsesFake | None):
        self._texto = texto
        self._uso = uso
        self.chamadas: list[dict] = []

    async def create(self, **kwargs):
        self.chamadas.append(kwargs)
        return _RespostaResponsesFake(self._texto, self._uso)


class _ChatCompletionsFake:
    def __init__(self, texto: str, uso: _UsoChatCompletionsFake | None):
        self._texto = texto
        self._uso = uso
        self.chamadas: list[dict] = []

    async def create(self, **kwargs):
        self.chamadas.append(kwargs)
        return _RespostaChatCompletionsFake(self._texto, self._uso)


class _ChatFake:
    def __init__(self, completions: _ChatCompletionsFake):
        self.completions = completions


class _ClienteOpenAIFake:
    """Só o suficiente de `openai.AsyncOpenAI` pra `ClienteOpenAICompativel`
    usar — `.responses.create` e `.chat.completions.create`."""

    def __init__(
        self,
        texto: str = "resposta",
        uso_responses: _UsoResponsesFake | None = None,
        uso_chat_completions: _UsoChatCompletionsFake | None = None,
    ):
        self.responses = _ResponsesFake(texto, uso_responses)
        self.chat = _ChatFake(_ChatCompletionsFake(texto, uso_chat_completions))


class TestChat:
    async def test_estilo_responses_usa_a_responses_api(self):
        cliente_real = _ClienteOpenAIFake("resposta via responses")
        cliente = ClienteOpenAICompativel(cliente_real, estilo_api="responses")

        resposta = await cliente.chat(
            model="openai.gpt-oss-120b", messages=[{"role": "user", "content": "oi"}]
        )

        assert len(cliente_real.responses.chamadas) == 1
        assert len(cliente_real.chat.completions.chamadas) == 0
        assert resposta.message.content == "resposta via responses"

    async def test_estilo_chat_completions_usa_chat_completions(self):
        cliente_real = _ClienteOpenAIFake("resposta via chat completions")
        cliente = ClienteOpenAICompativel(cliente_real, estilo_api="chat_completions")

        resposta = await cliente.chat(
            model="meta.llama-3.3-70b-instruct", messages=[{"role": "user", "content": "oi"}]
        )

        assert len(cliente_real.chat.completions.chamadas) == 1
        assert len(cliente_real.responses.chamadas) == 0
        assert resposta.message.content == "resposta via chat completions"

    async def test_estilo_padrao_do_construtor_e_chat_completions(self):
        # Sem passar `estilo_api` explícito — o padrão é o formato mais
        # comum (Chat Completions), não Responses API.
        cliente_real = _ClienteOpenAIFake()
        cliente = ClienteOpenAICompativel(cliente_real)

        await cliente.chat(
            model="qualquer-modelo", messages=[{"role": "user", "content": "oi"}]
        )

        assert len(cliente_real.chat.completions.chamadas) == 1
        assert len(cliente_real.responses.chamadas) == 0

    async def test_estilo_nao_depende_do_nome_do_modelo(self):
        # O nome do modelo não decide mais nada — só `estilo_api` decide,
        # mesmo pra um nome que antes disparava a Responses API.
        cliente_real = _ClienteOpenAIFake()
        cliente = ClienteOpenAICompativel(cliente_real, estilo_api="chat_completions")

        await cliente.chat(
            model="openai.gpt-oss-120b", messages=[{"role": "user", "content": "oi"}]
        )

        assert len(cliente_real.chat.completions.chamadas) == 1
        assert len(cliente_real.responses.chamadas) == 0

    async def test_chat_completions_recebe_as_mensagens_intactas(self):
        cliente_real = _ClienteOpenAIFake()
        cliente = ClienteOpenAICompativel(cliente_real)
        mensagens = [{"role": "system", "content": "sistema"}, {"role": "user", "content": "usuario"}]

        await cliente.chat(model="meta.llama-3.3-70b-instruct", messages=mensagens)

        assert cliente_real.chat.completions.chamadas[0]["messages"] == mensagens

    async def test_options_do_ollama_e_absorvido_sem_erro(self):
        # `options` (`num_ctx` etc) é linguagem do Ollama sem equivalente
        # aqui — o client protegido manda do mesmo jeito pra qualquer
        # provedor, e este client só ignora (`format`, ao contrário, É
        # traduzido — ver os testes de `TestFormatoEstruturado`).
        cliente_real = _ClienteOpenAIFake()
        cliente = ClienteOpenAICompativel(cliente_real)

        await cliente.chat(
            model="meta.llama-3.3-70b-instruct",
            messages=[{"role": "user", "content": "oi"}],
            options={"num_ctx": 1},
        )

    async def test_responses_api_normaliza_tokens_pro_formato_do_ollama(self):
        cliente_real = _ClienteOpenAIFake(uso_responses=_UsoResponsesFake(input_tokens=67, output_tokens=48))
        cliente = ClienteOpenAICompativel(cliente_real, estilo_api="responses")

        resposta = await cliente.chat(model="openai.gpt-oss-120b", messages=[{"role": "user", "content": "oi"}])

        assert resposta.prompt_eval_count == 67
        assert resposta.eval_count == 48

    async def test_chat_completions_normaliza_tokens_pro_formato_do_ollama(self):
        cliente_real = _ClienteOpenAIFake(
            uso_chat_completions=_UsoChatCompletionsFake(prompt_tokens=20, completion_tokens=15)
        )
        cliente = ClienteOpenAICompativel(cliente_real)

        resposta = await cliente.chat(
            model="meta.llama-3.3-70b-instruct", messages=[{"role": "user", "content": "oi"}]
        )

        assert resposta.prompt_eval_count == 20
        assert resposta.eval_count == 15

    async def test_usage_ausente_nao_quebra_e_grava_none(self):
        cliente_real = _ClienteOpenAIFake()  # usage=None nos dois fakes por padrão
        cliente = ClienteOpenAICompativel(cliente_real)

        resposta = await cliente.chat(
            model="meta.llama-3.3-70b-instruct", messages=[{"role": "user", "content": "oi"}]
        )

        assert resposta.prompt_eval_count is None
        assert resposta.eval_count is None

    async def test_responses_api_extrai_tokens_de_raciocinio(self):
        # Exemplo real do teste do suporte Oracle: 31 dos 48 tokens de
        # saída foram raciocínio, não resposta.
        cliente_real = _ClienteOpenAIFake(
            uso_responses=_UsoResponsesFake(
                input_tokens=67, output_tokens=48, output_tokens_details=_DetalhesSaidaFake(reasoning_tokens=31)
            )
        )
        cliente = ClienteOpenAICompativel(cliente_real, estilo_api="responses")

        resposta = await cliente.chat(model="openai.gpt-oss-120b", messages=[{"role": "user", "content": "oi"}])

        assert resposta.tokens_raciocinio == 31

    async def test_responses_api_sem_detalhes_de_saida_grava_none(self):
        cliente_real = _ClienteOpenAIFake(uso_responses=_UsoResponsesFake(input_tokens=67, output_tokens=48))
        cliente = ClienteOpenAICompativel(cliente_real, estilo_api="responses")

        resposta = await cliente.chat(model="openai.gpt-oss-120b", messages=[{"role": "user", "content": "oi"}])

        assert resposta.tokens_raciocinio is None

    async def test_chat_completions_nao_tem_conceito_de_raciocinio(self):
        # Chat Completions (Llama) não anexa `tokens_raciocinio` nenhum —
        # `cliente_protegido.py` sempre lê via `getattr(..., None)`,
        # exatamente por causa disso.
        cliente_real = _ClienteOpenAIFake(
            uso_chat_completions=_UsoChatCompletionsFake(prompt_tokens=20, completion_tokens=15)
        )
        cliente = ClienteOpenAICompativel(cliente_real)

        resposta = await cliente.chat(
            model="meta.llama-3.3-70b-instruct", messages=[{"role": "user", "content": "oi"}]
        )

        assert getattr(resposta, "tokens_raciocinio", None) is None


class TestFormatoEstruturado:
    """`format=SCHEMA` é como todo módulo de IA do projeto já pede saída
    estruturada (linguagem do `ollama.AsyncClient`) — regressão real:
    esse client absorvia e descartava, então o modelo respondia em texto
    livre com a OCI ativa (o julgamento de suficiência de chamado saía
    mais frouxo do que com o Ollama, que sempre respeitou o schema)."""

    async def test_responses_api_sem_format_nao_pede_saida_estruturada(self):
        cliente_real = _ClienteOpenAIFake()
        cliente = ClienteOpenAICompativel(cliente_real, estilo_api="responses")

        await cliente.chat(model="openai.gpt-oss-120b", messages=[{"role": "user", "content": "oi"}])

        assert "text" not in cliente_real.responses.chamadas[0]

    async def test_responses_api_com_format_pede_json_schema_no_text(self):
        cliente_real = _ClienteOpenAIFake()
        cliente = ClienteOpenAICompativel(cliente_real, estilo_api="responses")

        await cliente.chat(
            model="openai.gpt-oss-120b", messages=[{"role": "user", "content": "oi"}], format=_SCHEMA_TESTE
        )

        assert cliente_real.responses.chamadas[0]["text"] == {
            "format": {"type": "json_schema", "name": _NOME_SCHEMA, "schema": _SCHEMA_TESTE}
        }

    async def test_chat_completions_sem_format_nao_pede_saida_estruturada(self):
        cliente_real = _ClienteOpenAIFake()
        cliente = ClienteOpenAICompativel(cliente_real)

        await cliente.chat(model="meta.llama-3.3-70b-instruct", messages=[{"role": "user", "content": "oi"}])

        assert "response_format" not in cliente_real.chat.completions.chamadas[0]

    async def test_chat_completions_com_format_pede_json_schema_no_response_format(self):
        cliente_real = _ClienteOpenAIFake()
        cliente = ClienteOpenAICompativel(cliente_real)

        await cliente.chat(
            model="meta.llama-3.3-70b-instruct",
            messages=[{"role": "user", "content": "oi"}],
            format=_SCHEMA_TESTE,
        )

        assert cliente_real.chat.completions.chamadas[0]["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": _NOME_SCHEMA, "schema": _SCHEMA_TESTE},
        }


class TestEmbed:
    async def test_sempre_levanta_embedding_nao_suportado(self):
        cliente = ClienteOpenAICompativel(_ClienteOpenAIFake())

        with pytest.raises(EmbeddingNaoSuportado):
            await cliente.embed(model="qualquer", input="texto")
