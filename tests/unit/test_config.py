import pytest

from agente_oracle.config import (
    TAMANHO_MINIMO_AUTH_SECRET_KEY,
    Settings,
    ollama_api_key_do_dominio,
    ollama_host_do_dominio,
    ollama_model_do_dominio,
    validar_auth_secret_key,
    validar_glpi_configurado,
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


class TestValidarGlpiConfigurado:
    def test_sem_base_url_nao_valida_nada(self):
        # glpi_client_id/secret vazios não importa — sem base_url, nada
        # aqui é obrigatório (só a funcionalidade de TI não funciona).
        validar_glpi_configurado(Settings(glpi_base_url=""))

    def test_base_url_sem_client_id_ou_secret_levanta_erro(self):
        # Limpa os 4 campos explicitamente — sem isso, `Settings()` herdaria
        # os valores reais do `.env` local (quando preenchido) em vez do
        # cenário "faltando" que este teste quer exercitar.
        with pytest.raises(RuntimeError, match="GLPI_CLIENT_ID"):
            validar_glpi_configurado(
                Settings(
                    glpi_base_url="https://glpi.exemplo.com",
                    glpi_client_id="",
                    glpi_client_secret="",
                    glpi_username="",
                    glpi_password="",
                )
            )

    def test_base_url_e_client_sem_usuario_ou_senha_levanta_erro(self):
        with pytest.raises(RuntimeError, match="GLPI_USERNAME"):
            validar_glpi_configurado(
                Settings(
                    glpi_base_url="https://glpi.exemplo.com",
                    glpi_client_id="id",
                    glpi_client_secret="segredo",
                    glpi_username="",
                    glpi_password="",
                )
            )

    def test_base_url_e_credenciais_sem_webhook_secret_levanta_erro(self):
        with pytest.raises(RuntimeError, match="GLPI_WEBHOOK_SECRET"):
            validar_glpi_configurado(
                Settings(
                    glpi_base_url="https://glpi.exemplo.com",
                    glpi_client_id="id",
                    glpi_client_secret="segredo",
                    glpi_username="usuario",
                    glpi_password="senha",
                    glpi_webhook_secret="curto",
                )
            )

    def test_tudo_preenchido_com_tamanho_suficiente_nao_levanta_erro(self):
        validar_glpi_configurado(
            Settings(
                glpi_base_url="https://glpi.exemplo.com",
                glpi_client_id="id",
                glpi_client_secret="segredo",
                glpi_username="usuario",
                glpi_password="senha",
                glpi_webhook_secret="x" * TAMANHO_MINIMO_AUTH_SECRET_KEY,
            )
        )


class TestOllamaHostDoDominio:
    def test_sem_override_usa_o_host_global(self):
        settings = Settings(ollama_host="http://127.0.0.1:11434", ollama_host_ti="")
        assert ollama_host_do_dominio(settings, "ti") == "http://127.0.0.1:11434"

    def test_com_override_usa_o_host_do_dominio(self):
        settings = Settings(ollama_host="http://127.0.0.1:11434", ollama_host_ti="https://ollama.com")
        assert ollama_host_do_dominio(settings, "ti") == "https://ollama.com"


class TestOllamaModelDoDominio:
    def test_sem_override_usa_o_modelo_global(self):
        settings = Settings(ollama_model="qwen2.5-coder:7b", ollama_model_financeiro="")
        assert ollama_model_do_dominio(settings, "financeiro") == "qwen2.5-coder:7b"

    def test_com_override_usa_o_modelo_do_dominio(self):
        settings = Settings(ollama_model="qwen2.5-coder:7b", ollama_model_ti="gpt-oss:120b")
        assert ollama_model_do_dominio(settings, "ti") == "gpt-oss:120b"


class TestOllamaApiKeyDoDominio:
    def test_sem_override_devolve_vazio(self):
        assert ollama_api_key_do_dominio(Settings(ollama_api_key_ti=""), "ti") == ""

    def test_com_override_devolve_a_chave_do_dominio(self):
        assert ollama_api_key_do_dominio(Settings(ollama_api_key_rh="abc123"), "rh") == "abc123"


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

    def test_dominio_ti_remoto_com_oracle_e_global_local_nao_levanta_erro(self):
        # TI não toca Oracle — pode ser liberado sozinho, mesmo com o resto travado.
        validar_ollama_host_seguro(
            Settings(
                db_backend="oracle",
                ollama_host="http://127.0.0.1:11434",
                ollama_host_ti="https://ollama.com",
            )
        )

    def test_dominio_financeiro_remoto_com_oracle_levanta_erro_citando_o_dominio(self):
        settings = Settings(
            db_backend="oracle",
            ollama_host="http://127.0.0.1:11434",
            ollama_host_financeiro="https://ollama.com",
        )
        with pytest.raises(RuntimeError, match="OLLAMA_HOST_FINANCEIRO"):
            validar_ollama_host_seguro(settings)

    def test_dominio_ti_local_explicito_com_oracle_nao_levanta_erro(self):
        validar_ollama_host_seguro(
            Settings(
                db_backend="oracle",
                ollama_host="http://127.0.0.1:11434",
                ollama_host_ti="http://127.0.0.1:11434",
            )
        )
