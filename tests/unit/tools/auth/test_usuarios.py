from agente_oracle.tools.auth.usuarios import TAMANHO_MINIMO_SENHA, senha_fraca


class TestSenhaFraca:
    def test_senha_curta_e_rejeitada(self):
        assert senha_fraca("x" * (TAMANHO_MINIMO_SENHA - 1)) is not None

    def test_senha_com_tamanho_minimo_e_aceita(self):
        assert senha_fraca("x" * TAMANHO_MINIMO_SENHA) is None

    def test_senha_vazia_e_rejeitada(self):
        assert senha_fraca("") is not None
