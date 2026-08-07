import pytest

from agente_oracle.config import TAMANHO_MINIMO_AUTH_SECRET_KEY, Settings, validar_auth_secret_key


class TestValidarAuthSecretKey:
    def test_chave_vazia_levanta_erro(self):
        with pytest.raises(RuntimeError, match="AUTH_SECRET_KEY"):
            validar_auth_secret_key(Settings(auth_secret_key=""))

    def test_chave_curta_demais_levanta_erro(self):
        with pytest.raises(RuntimeError, match="AUTH_SECRET_KEY"):
            validar_auth_secret_key(Settings(auth_secret_key="x" * (TAMANHO_MINIMO_AUTH_SECRET_KEY - 1)))

    def test_chave_com_tamanho_suficiente_nao_levanta_erro(self):
        validar_auth_secret_key(Settings(auth_secret_key="x" * TAMANHO_MINIMO_AUTH_SECRET_KEY))
