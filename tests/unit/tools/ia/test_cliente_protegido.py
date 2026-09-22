import logging

from agente_oracle.config import Settings
from agente_oracle.tools.ia import auditoria_externa
from agente_oracle.tools.ia import cliente_protegido as mod
from agente_oracle.tools.ia.cliente_protegido import ClienteOllamaProtegido, criar_cliente_protegido


class _ClienteRealFake:
    def __init__(self):
        self.chamadas_chat: list[dict] = []
        self.chamadas_embed: list[dict] = []

    async def chat(self, **kwargs):
        self.chamadas_chat.append(kwargs)
        return "resposta-chat"

    async def embed(self, **kwargs):
        self.chamadas_embed.append(kwargs)
        return "resposta-embed"


def _sem_auditoria_real(monkeypatch, contagem: int = 0) -> list[tuple]:
    """Substitui `auditoria_externa` por dublês — o wrapper não deve tocar
    Postgres de verdade num teste unitário."""
    registros: list[tuple] = []
    monkeypatch.setattr(auditoria_externa, "registrar", lambda *args: registros.append(args))
    monkeypatch.setattr(auditoria_externa, "contagem_hoje", lambda _dominio: contagem)
    return registros


class TestClienteOllamaProtegidoChat:
    async def test_sanitizar_true_mascara_antes_de_repassar(self, monkeypatch):
        _sem_auditoria_real(monkeypatch)
        cliente_real = _ClienteRealFake()
        protegido = ClienteOllamaProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500)

        await protegido.chat(model="modelo-teste", messages=[{"role": "user", "content": "CPF 123.456.789-00"}])

        conteudo = cliente_real.chamadas_chat[0]["messages"][0]["content"]
        assert "123.456.789-00" not in conteudo
        assert "[CPF]" in conteudo

    async def test_sanitizar_false_repassa_intacto(self, monkeypatch):
        # deteccao_seguranca.py: usuario/usuario_id é o objeto do achado.
        _sem_auditoria_real(monkeypatch)
        cliente_real = _ClienteRealFake()
        protegido = ClienteOllamaProtegido(cliente_real, "ti", "http://127.0.0.1:11434", False, 500)

        await protegido.chat(model="modelo-teste", messages=[{"role": "user", "content": "usuario joao@empresa.com"}])

        assert cliente_real.chamadas_chat[0]["messages"][0]["content"] == "usuario joao@empresa.com"

    async def test_grava_auditoria_com_dominio_e_host(self, monkeypatch):
        registros = _sem_auditoria_real(monkeypatch)
        cliente_real = _ClienteRealFake()
        protegido = ClienteOllamaProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500)

        await protegido.chat(model="m", messages=[{"role": "user", "content": "oi"}])

        dominio, host, _texto = registros[0]
        assert dominio == "ti"
        assert host == "http://127.0.0.1:11434"

    async def test_kwargs_extras_chegam_intactos_no_client_real(self, monkeypatch):
        _sem_auditoria_real(monkeypatch)
        cliente_real = _ClienteRealFake()
        protegido = ClienteOllamaProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500)

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
        protegido = ClienteOllamaProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500)

        resposta = await protegido.chat(model="m", messages=[{"role": "user", "content": "oi"}])

        assert resposta == "resposta-chat"

    async def test_teto_excedido_gera_warning_no_log_sem_bloquear(self, monkeypatch, caplog):
        _sem_auditoria_real(monkeypatch, contagem=501)
        cliente_real = _ClienteRealFake()
        protegido = ClienteOllamaProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500)

        with caplog.at_level(logging.WARNING):
            resposta = await protegido.chat(model="m", messages=[{"role": "user", "content": "oi"}])

        assert "teto" in caplog.text.lower()
        assert resposta == "resposta-chat"  # o alerta não impede a chamada

    async def test_teto_nao_excedido_nao_gera_warning(self, monkeypatch, caplog):
        _sem_auditoria_real(monkeypatch, contagem=10)
        cliente_real = _ClienteRealFake()
        protegido = ClienteOllamaProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500)

        with caplog.at_level(logging.WARNING):
            await protegido.chat(model="m", messages=[{"role": "user", "content": "oi"}])

        assert caplog.text == ""


class TestClienteOllamaProtegidoEmbed:
    async def test_sanitizar_true_mascara_antes_de_repassar(self, monkeypatch):
        _sem_auditoria_real(monkeypatch)
        cliente_real = _ClienteRealFake()
        protegido = ClienteOllamaProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500)

        await protegido.embed(model="modelo-embed", input="CPF 123.456.789-00")

        texto_enviado = cliente_real.chamadas_embed[0]["input"]
        assert "123.456.789-00" not in texto_enviado
        assert "[CPF]" in texto_enviado

    async def test_sanitizar_false_repassa_intacto(self, monkeypatch):
        _sem_auditoria_real(monkeypatch)
        cliente_real = _ClienteRealFake()
        protegido = ClienteOllamaProtegido(cliente_real, "ti", "http://127.0.0.1:11434", False, 500)

        await protegido.embed(model="modelo-embed", input="CPF 123.456.789-00")

        assert cliente_real.chamadas_embed[0]["input"] == "CPF 123.456.789-00"

    async def test_grava_auditoria(self, monkeypatch):
        registros = _sem_auditoria_real(monkeypatch)
        cliente_real = _ClienteRealFake()
        protegido = ClienteOllamaProtegido(cliente_real, "ti", "http://127.0.0.1:11434", True, 500)

        await protegido.embed(model="modelo-embed", input="texto qualquer")

        assert len(registros) == 1


class TestCriarClienteProtegido:
    def test_client_real_usa_o_host_resolvido_do_dominio(self, monkeypatch):
        chamadas = []

        class _AsyncClientFake:
            def __init__(self, **kwargs):
                chamadas.append(kwargs)

        monkeypatch.setattr(mod, "AsyncClient", _AsyncClientFake)
        settings = Settings(ollama_host="http://127.0.0.1:11434", ollama_host_ti="https://ollama.com")

        criar_cliente_protegido(settings, "ti", sanitizar=True)

        assert chamadas[0]["host"] == "https://ollama.com"

    def test_inclui_header_de_autenticacao_quando_ha_api_key_do_dominio(self, monkeypatch):
        chamadas = []

        class _AsyncClientFake:
            def __init__(self, **kwargs):
                chamadas.append(kwargs)

        monkeypatch.setattr(mod, "AsyncClient", _AsyncClientFake)
        settings = Settings(ollama_api_key_ti="segredo123")

        criar_cliente_protegido(settings, "ti", sanitizar=True)

        assert chamadas[0]["headers"] == {"Authorization": "Bearer segredo123"}

    def test_sem_api_key_nao_manda_header_nenhum(self, monkeypatch):
        chamadas = []

        class _AsyncClientFake:
            def __init__(self, **kwargs):
                chamadas.append(kwargs)

        monkeypatch.setattr(mod, "AsyncClient", _AsyncClientFake)
        settings = Settings(ollama_api_key_ti="")

        criar_cliente_protegido(settings, "ti", sanitizar=True)

        assert chamadas[0]["headers"] == {}

    async def test_usa_o_teto_diario_configurado(self, monkeypatch, caplog):
        monkeypatch.setattr(mod, "AsyncClient", lambda **_kwargs: _ClienteRealFake())
        _sem_auditoria_real(monkeypatch, contagem=51)
        settings = Settings(teto_diario_ia_externa=50)
        protegido = criar_cliente_protegido(settings, "ti", sanitizar=True)

        with caplog.at_level(logging.WARNING):
            await protegido.chat(model="m", messages=[{"role": "user", "content": "oi"}])

        assert "teto" in caplog.text.lower()
