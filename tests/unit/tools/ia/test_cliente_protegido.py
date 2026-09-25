import logging
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from agente_oracle.config import Settings
from agente_oracle.tools.ia import auditoria_externa, configuracoes_provedor, provedores_llm
from agente_oracle.tools.ia import cliente_protegido as mod
from agente_oracle.tools.ia.cliente_protegido import (
    ClienteIAProtegido,
    criar_cliente_protegido,
    modelo_ia_ativo,
)
from agente_oracle.tools.ia.provedores_llm import ProvedorLLM


def _provedor_llm(**overrides) -> ProvedorLLM:
    campos = {
        "id": 1,
        "nome": "OCI Generative AI — gpt-oss-120b",
        "tipo_conexao": "openai_compativel",
        "base_url": "https://inference.generativeai.sa-saopaulo-1.oci.oraclecloud.com/openai/v1",
        "api_key": "sk-segredo",
        "projeto_id": "ocid1.generativeaiproject.oc1...",
        "modelo": "openai.gpt-oss-120b",
        "estilo_api": "responses",
        "preco_entrada_por_1k": Decimal("0"),
        "preco_saida_por_1k": Decimal("0"),
        "moeda": "R$",
        "criado_em": datetime.now(UTC),
    }
    campos.update(overrides)
    return ProvedorLLM(**campos)


def _sem_cadastro_ativo(monkeypatch) -> None:
    """`criar_cliente_protegido`/`modelo_ia_ativo` caem no Ollama padrão do
    `.env` quando não há nenhum LLM cadastrado ativo — mocka
    `provedor_llm_ativo_id` pra `None`, sem precisar de banco real num
    teste unitário."""
    monkeypatch.setattr(configuracoes_provedor, "provedor_llm_ativo_id", lambda: None)


def _com_cadastro_ativo(monkeypatch, provedor: ProvedorLLM) -> None:
    monkeypatch.setattr(configuracoes_provedor, "provedor_llm_ativo_id", lambda: provedor.id)
    monkeypatch.setattr(provedores_llm, "buscar", lambda _id: provedor)


class _ClienteRealFake:
    def __init__(self, resposta_chat: object = "resposta-chat"):
        self.chamadas_chat: list[dict] = []
        self.chamadas_embed: list[dict] = []
        self._resposta_chat = resposta_chat

    async def chat(self, **kwargs):
        self.chamadas_chat.append(kwargs)
        return self._resposta_chat

    async def embed(self, **kwargs):
        self.chamadas_embed.append(kwargs)
        return "resposta-embed"


def _sem_auditoria_real(
    monkeypatch, contagem: int = 0, teto_tokens: int = 0, tokens_hoje: int = 0
) -> list[tuple]:
    """Substitui `auditoria_externa`/`configuracoes_provedor` por dublês —
    o wrapper não deve tocar Postgres de verdade num teste unitário.
    `teto_tokens=0` (padrão) é "sem teto", então `_avisar_teto_tokens` nem
    chega a chamar `tokens_hoje` na maioria dos testes."""
    registros: list[tuple] = []
    monkeypatch.setattr(auditoria_externa, "registrar", lambda *args: registros.append(args))
    monkeypatch.setattr(auditoria_externa, "contagem_hoje", lambda _dominio: contagem)
    monkeypatch.setattr(auditoria_externa, "tokens_hoje", lambda _dominio: tokens_hoje)
    monkeypatch.setattr(configuracoes_provedor, "teto_tokens_diario", lambda: teto_tokens)
    return registros


class TestClienteIAProtegidoChat:
    async def test_sanitizar_true_mascara_antes_de_repassar(self, monkeypatch):
        _sem_auditoria_real(monkeypatch)
        cliente_real = _ClienteRealFake()
        protegido = ClienteIAProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500, "ollama", "usuario-teste")

        await protegido.chat(model="modelo-teste", messages=[{"role": "user", "content": "CPF 123.456.789-00"}])

        conteudo = cliente_real.chamadas_chat[0]["messages"][0]["content"]
        assert "123.456.789-00" not in conteudo
        assert "[CPF]" in conteudo

    async def test_sanitizar_false_repassa_intacto(self, monkeypatch):
        # deteccao_seguranca.py: usuario/usuario_id é o objeto do achado.
        _sem_auditoria_real(monkeypatch)
        cliente_real = _ClienteRealFake()
        protegido = ClienteIAProtegido(cliente_real, "ti", "http://127.0.0.1:11434", False, 500, "ollama", "usuario-teste")

        await protegido.chat(model="modelo-teste", messages=[{"role": "user", "content": "usuario joao@empresa.com"}])

        assert cliente_real.chamadas_chat[0]["messages"][0]["content"] == "usuario joao@empresa.com"

    async def test_grava_auditoria_com_dominio_host_provedor_e_modelo(self, monkeypatch):
        registros = _sem_auditoria_real(monkeypatch)
        cliente_real = _ClienteRealFake()
        protegido = ClienteIAProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500, "ollama", "usuario-teste")

        await protegido.chat(model="modelo-teste", messages=[{"role": "user", "content": "oi"}])

        dominio, host, _texto, provedor, modelo, _te, _ts, _tr, usuario_id = registros[0]
        assert dominio == "ti"
        assert host == "http://127.0.0.1:11434"
        assert provedor == "ollama"
        assert modelo == "modelo-teste"
        assert usuario_id == "usuario-teste"

    async def test_grava_os_tokens_da_resposta(self, monkeypatch):
        registros = _sem_auditoria_real(monkeypatch)
        cliente_real = _ClienteRealFake(
            resposta_chat=SimpleNamespace(
                message=SimpleNamespace(content="oi"),
                prompt_eval_count=7,
                eval_count=3,
                tokens_raciocinio=2,
            )
        )
        protegido = ClienteIAProtegido(
            cliente_real, "ti", "http://127.0.0.1:11434", True, 500, "OCI Generative AI — gpt-oss-120b", "usuario-teste"
        )

        await protegido.chat(model="m", messages=[{"role": "user", "content": "oi"}])

        *_resto, tokens_entrada, tokens_saida, tokens_raciocinio, _usuario_id = registros[0]
        assert tokens_entrada == 7
        assert tokens_saida == 3
        assert tokens_raciocinio == 2

    async def test_resposta_sem_atributo_de_token_grava_none(self, monkeypatch):
        # Resposta simples (ex: string), sem `prompt_eval_count`/`eval_count`
        # — não pode quebrar o registro, só grava None.
        registros = _sem_auditoria_real(monkeypatch)
        cliente_real = _ClienteRealFake()
        protegido = ClienteIAProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500, "ollama", "usuario-teste")

        await protegido.chat(model="m", messages=[{"role": "user", "content": "oi"}])

        *_resto, tokens_entrada, tokens_saida, tokens_raciocinio, _usuario_id = registros[0]
        assert tokens_entrada is None
        assert tokens_saida is None
        assert tokens_raciocinio is None

    async def test_kwargs_extras_chegam_intactos_no_client_real(self, monkeypatch):
        _sem_auditoria_real(monkeypatch)
        cliente_real = _ClienteRealFake()
        protegido = ClienteIAProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500, "ollama", "usuario-teste")

        await protegido.chat(
            model="modelo-teste",
            messages=[{"role": "user", "content": "oi"}],
            format={"type": "object"},
            options={"num_ctx": 1},
        )

        chamada = cliente_real.chamadas_chat[0]
        assert chamada["model"] == "modelo-teste"
        assert chamada["format"] == {"type": "object"}
        assert chamada["options"] == {"num_ctx": 1}

    async def test_devolve_a_resposta_do_client_real(self, monkeypatch):
        _sem_auditoria_real(monkeypatch)
        cliente_real = _ClienteRealFake()
        protegido = ClienteIAProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500, "ollama", "usuario-teste")

        resposta = await protegido.chat(model="m", messages=[{"role": "user", "content": "oi"}])

        assert resposta == "resposta-chat"

    async def test_teto_excedido_gera_warning_no_log_sem_bloquear(self, monkeypatch, caplog):
        _sem_auditoria_real(monkeypatch, contagem=501)
        cliente_real = _ClienteRealFake()
        protegido = ClienteIAProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500, "ollama", "usuario-teste")

        with caplog.at_level(logging.WARNING):
            resposta = await protegido.chat(model="m", messages=[{"role": "user", "content": "oi"}])

        assert "teto" in caplog.text.lower()
        assert resposta == "resposta-chat"  # o alerta não impede a chamada

    async def test_teto_nao_excedido_nao_gera_warning(self, monkeypatch, caplog):
        _sem_auditoria_real(monkeypatch, contagem=10)
        cliente_real = _ClienteRealFake()
        protegido = ClienteIAProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500, "ollama", "usuario-teste")

        with caplog.at_level(logging.WARNING):
            await protegido.chat(model="m", messages=[{"role": "user", "content": "oi"}])

        assert caplog.text == ""

    async def test_teto_de_tokens_excedido_gera_warning_sem_bloquear(self, monkeypatch, caplog):
        _sem_auditoria_real(monkeypatch, teto_tokens=100, tokens_hoje=150)
        cliente_real = _ClienteRealFake()
        protegido = ClienteIAProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500, "ollama", "usuario-teste")

        with caplog.at_level(logging.WARNING):
            resposta = await protegido.chat(model="m", messages=[{"role": "user", "content": "oi"}])

        assert "teto" in caplog.text.lower()
        assert "token" in caplog.text.lower()
        assert resposta == "resposta-chat"

    async def test_sem_teto_de_tokens_configurado_nunca_avisa(self, monkeypatch, caplog):
        _sem_auditoria_real(monkeypatch, teto_tokens=0, tokens_hoje=999999)
        cliente_real = _ClienteRealFake()
        protegido = ClienteIAProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500, "ollama", "usuario-teste")

        with caplog.at_level(logging.WARNING):
            await protegido.chat(model="m", messages=[{"role": "user", "content": "oi"}])

        assert caplog.text == ""


class TestClienteIAProtegidoEmbed:
    async def test_sanitizar_true_mascara_antes_de_repassar(self, monkeypatch):
        _sem_auditoria_real(monkeypatch)
        cliente_real = _ClienteRealFake()
        protegido = ClienteIAProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500, "ollama", "usuario-teste")

        await protegido.embed(model="modelo-embed", input="CPF 123.456.789-00")

        texto_enviado = cliente_real.chamadas_embed[0]["input"]
        assert "123.456.789-00" not in texto_enviado
        assert "[CPF]" in texto_enviado

    async def test_sanitizar_false_repassa_intacto(self, monkeypatch):
        _sem_auditoria_real(monkeypatch)
        cliente_real = _ClienteRealFake()
        protegido = ClienteIAProtegido(cliente_real, "ti", "http://127.0.0.1:11434", False, 500, "ollama", "usuario-teste")

        await protegido.embed(model="modelo-embed", input="CPF 123.456.789-00")

        assert cliente_real.chamadas_embed[0]["input"] == "CPF 123.456.789-00"

    async def test_grava_auditoria(self, monkeypatch):
        registros = _sem_auditoria_real(monkeypatch)
        cliente_real = _ClienteRealFake()
        protegido = ClienteIAProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500, "ollama", "usuario-teste")

        await protegido.embed(model="modelo-embed", input="texto qualquer")

        assert len(registros) == 1

    async def test_grava_modelo_e_tokens_de_entrada(self, monkeypatch):
        registros = _sem_auditoria_real(monkeypatch)
        cliente_real = _ClienteRealFake()
        cliente_real.embed = _embed_com_tokens
        protegido = ClienteIAProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500, "ollama", "usuario-teste")

        await protegido.embed(model="modelo-embed", input="texto qualquer")

        (
            _dominio,
            _host,
            _texto,
            _provedor,
            modelo,
            tokens_entrada,
            tokens_saida,
            tokens_raciocinio,
            usuario_id,
        ) = registros[0]
        assert modelo == "modelo-embed"
        assert tokens_entrada == 9
        assert tokens_saida is None
        assert tokens_raciocinio is None
        assert usuario_id == "usuario-teste"


async def _embed_com_tokens(**_kwargs):
    return SimpleNamespace(embeddings=[[0.1, 0.2]], prompt_eval_count=9)


class TestCriarClienteProtegido:
    def test_client_real_usa_o_host_resolvido_do_dominio(self, monkeypatch):
        _sem_cadastro_ativo(monkeypatch)
        chamadas = []

        class _AsyncClientFake:
            def __init__(self, **kwargs):
                chamadas.append(kwargs)

        monkeypatch.setattr(mod, "AsyncClient", _AsyncClientFake)
        settings = Settings(ollama_host="http://127.0.0.1:11434", ollama_host_ti="https://ollama.com")

        criar_cliente_protegido(settings, "ti", sanitizar=True, usuario_id="usuario-teste")

        assert chamadas[0]["host"] == "https://ollama.com"

    def test_inclui_header_de_autenticacao_quando_ha_api_key_do_dominio(self, monkeypatch):
        _sem_cadastro_ativo(monkeypatch)
        chamadas = []

        class _AsyncClientFake:
            def __init__(self, **kwargs):
                chamadas.append(kwargs)

        monkeypatch.setattr(mod, "AsyncClient", _AsyncClientFake)
        settings = Settings(ollama_api_key_ti="segredo123")

        criar_cliente_protegido(settings, "ti", sanitizar=True, usuario_id="usuario-teste")

        assert chamadas[0]["headers"] == {"Authorization": "Bearer segredo123"}

    def test_sem_api_key_nao_manda_header_nenhum(self, monkeypatch):
        _sem_cadastro_ativo(monkeypatch)
        chamadas = []

        class _AsyncClientFake:
            def __init__(self, **kwargs):
                chamadas.append(kwargs)

        monkeypatch.setattr(mod, "AsyncClient", _AsyncClientFake)
        settings = Settings(ollama_api_key_ti="")

        criar_cliente_protegido(settings, "ti", sanitizar=True, usuario_id="usuario-teste")

        assert chamadas[0]["headers"] == {}

    async def test_usa_o_teto_diario_configurado(self, monkeypatch, caplog):
        _sem_cadastro_ativo(monkeypatch)
        monkeypatch.setattr(mod, "AsyncClient", lambda **_kwargs: _ClienteRealFake())
        _sem_auditoria_real(monkeypatch, contagem=51)
        settings = Settings(teto_diario_ia_externa=50)
        protegido = criar_cliente_protegido(settings, "ti", sanitizar=True, usuario_id="usuario-teste")

        with caplog.at_level(logging.WARNING):
            await protegido.chat(model="m", messages=[{"role": "user", "content": "oi"}])

        assert "teto" in caplog.text.lower()

    def test_provedor_openai_compativel_monta_client_openai_com_o_cadastro_ativo(self, monkeypatch):
        provedor = _provedor_llm()
        _com_cadastro_ativo(monkeypatch, provedor)
        chamadas = []

        class _AsyncOpenAIFake:
            def __init__(self, **kwargs):
                chamadas.append(kwargs)

        monkeypatch.setattr(mod, "AsyncOpenAI", _AsyncOpenAIFake)

        cliente = criar_cliente_protegido(Settings(), "ti", sanitizar=True, usuario_id="usuario-teste")

        assert chamadas[0]["base_url"] == provedor.base_url
        assert chamadas[0]["api_key"] == provedor.api_key
        assert chamadas[0]["project"] == provedor.projeto_id
        assert isinstance(cliente._cliente, mod.ClienteOpenAICompativel)
        assert cliente._cliente._estilo_api == "responses"
        assert cliente._provedor == provedor.nome

    def test_provedor_ollama_cadastrado_monta_asyncclient_com_o_base_url_do_cadastro(self, monkeypatch):
        provedor = _provedor_llm(tipo_conexao="ollama", base_url="https://ollama-cadastrado.com", api_key="chave")
        _com_cadastro_ativo(monkeypatch, provedor)
        chamadas = []
        monkeypatch.setattr(mod, "AsyncClient", lambda **kwargs: chamadas.append(kwargs) or _ClienteRealFake())

        cliente = criar_cliente_protegido(Settings(), "ti", sanitizar=True, usuario_id="usuario-teste")

        assert chamadas[0]["host"] == "https://ollama-cadastrado.com"
        assert chamadas[0]["headers"] == {"Authorization": "Bearer chave"}
        assert cliente._provedor == provedor.nome

    def test_registro_vazio_cai_no_ollama_padrao_como_antes_do_cadastro_existir(self, monkeypatch):
        # Regressão: sem nenhum LLM cadastrado ativo não muda nada do
        # comportamento de antes do cadastro existir.
        _sem_cadastro_ativo(monkeypatch)
        chamadas = []
        monkeypatch.setattr(mod, "AsyncClient", lambda **kwargs: chamadas.append(kwargs))

        cliente = criar_cliente_protegido(Settings(), "ti", sanitizar=True, usuario_id="usuario-teste")

        assert len(chamadas) == 1
        assert cliente._provedor == mod._PROVEDOR_OLLAMA_PADRAO

    def test_dominio_financeiro_nunca_consulta_o_cadastro_mesmo_com_algo_ativo(self, monkeypatch):
        provedor = _provedor_llm()
        _com_cadastro_ativo(monkeypatch, provedor)
        chamadas = []
        monkeypatch.setattr(mod, "AsyncClient", lambda **kwargs: chamadas.append(kwargs))

        cliente = criar_cliente_protegido(Settings(), "financeiro", sanitizar=True, usuario_id="usuario-teste")

        assert len(chamadas) == 1  # Ollama do .env, não a OpenAI do cadastro
        assert cliente._provedor == mod._PROVEDOR_OLLAMA_PADRAO

    async def test_repassa_o_usuario_id_recebido_pra_auditoria(self, monkeypatch):
        _sem_cadastro_ativo(monkeypatch)
        registros = _sem_auditoria_real(monkeypatch)
        monkeypatch.setattr(mod, "AsyncClient", lambda **_kwargs: _ClienteRealFake())
        settings = Settings()

        protegido = criar_cliente_protegido(settings, "ti", sanitizar=True, usuario_id="42")
        await protegido.chat(model="m", messages=[{"role": "user", "content": "oi"}])

        assert registros[0][-1] == "42"

    async def test_usuario_sistema_e_repassado_igual_a_qualquer_outro_id(self, monkeypatch):
        _sem_cadastro_ativo(monkeypatch)
        registros = _sem_auditoria_real(monkeypatch)
        monkeypatch.setattr(mod, "AsyncClient", lambda **_kwargs: _ClienteRealFake())
        settings = Settings()

        protegido = criar_cliente_protegido(settings, "ti", sanitizar=True, usuario_id=mod.USUARIO_SISTEMA)
        await protegido.chat(model="m", messages=[{"role": "user", "content": "oi"}])

        assert registros[0][-1] == "sistema"


class TestModeloIaAtivo:
    def test_sem_cadastro_ativo_usa_o_padrao_do_dominio_no_ollama(self, monkeypatch):
        _sem_cadastro_ativo(monkeypatch)
        settings = Settings(ollama_model="qwen2.5-coder:7b", ollama_model_ti="")

        assert modelo_ia_ativo(settings, "ti") == "qwen2.5-coder:7b"

    def test_com_cadastro_ativo_usa_o_modelo_cadastrado(self, monkeypatch):
        _com_cadastro_ativo(monkeypatch, _provedor_llm(modelo="llama3:70b"))

        assert modelo_ia_ativo(Settings(), "ti") == "llama3:70b"

    def test_dominio_financeiro_nunca_consulta_o_cadastro_mesmo_com_algo_ativo(self, monkeypatch):
        _com_cadastro_ativo(monkeypatch, _provedor_llm(modelo="llama3:70b"))
        settings = Settings(ollama_model="qwen2.5-coder:7b")

        assert modelo_ia_ativo(settings, "financeiro") == "qwen2.5-coder:7b"
