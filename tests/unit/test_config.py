import pytest

from agente_oracle.config import (
    TAMANHO_MINIMO_AUTH_SECRET_KEY,
    Settings,
    validar_auth_secret_key,
    validar_ollama_host_seguro,
)


class TestValidarAuthSecretKey:
    def test_chave_vazia_levanta_erro(self):
        with pytest.raises(RuntimeError, match="AUTH_SECRET_KEY"):
            validar_auth_secret_key(Settings(auth_secret_key=""))

    def test_chave_curta_demais_levanta_erro(self):
        with pytest.raises(RuntimeError, match="AUTH_SECRET_KEY"):
            validar_auth_secret_key(Settings(auth_secret_key="x" * (TAMANHO_MINIMO_AUTH_SECRET_KEY - 1)))

    def test_chave_com_tamanho_suficiente_nao_levanta_erro(self):
        validar_auth_secret_key(Settings(auth_secret_key="x" * TAMANHO_MINIMO_AUTH_SECRET_KEY))


class TestValidarOllamaHostSeguro:
    def test_host_remoto_com_oracle_levanta_erro(self):
        settings = Settings(db_backend="oracle", ollama_host="http://203.0.113.10:11434")
        with pytest.raises(RuntimeError, match="OLLAMA_HOST"):
            validar_ollama_host_seguro(settings)

    def test_host_local_com_oracle_nao_levanta_erro(self):
        validar_ollama_host_seguro(Settings(db_backend="oracle", ollama_host="http://127.0.0.1:11434"))

    def test_host_com_localhost_nao_levanta_erro(self):
        validar_ollama_host_seguro(Settings(db_backend="oracle", ollama_host="http://localhost:11434"))

    def test_host_remoto_com_postgres_nao_levanta_erro(self):
        # Banco fictício, sem dado real da empresa — seguro usar IA remota.
        validar_ollama_host_seguro(Settings(db_backend="postgres", ollama_host="http://203.0.113.10:11434"))
