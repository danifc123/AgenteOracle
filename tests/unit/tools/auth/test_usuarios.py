from agente_oracle.tools.auth.usuarios import (
    _INDICE_EMAIL_UNICO,
    TAMANHO_MINIMO_SENHA,
    _email_duplicado,
    senha_fraca,
)


class TestSenhaFraca:
    def test_senha_curta_e_rejeitada(self):
        assert senha_fraca("x" * (TAMANHO_MINIMO_SENHA - 1)) is not None

    def test_senha_com_tamanho_minimo_e_aceita(self):
        assert senha_fraca("x" * TAMANHO_MINIMO_SENHA) is None

    def test_senha_vazia_e_rejeitada(self):
        assert senha_fraca("") is not None


class _ErroFake:
    """Imita o formato de um `psycopg.Error` só no que `_email_duplicado`
    olha (`erro.diag.constraint_name`) — sem precisar de um erro real do
    driver pra testar a função pura."""

    class _Diag:
        def __init__(self, constraint_name):
            self.constraint_name = constraint_name

    def __init__(self, constraint_name=None):
        self.diag = self._Diag(constraint_name)


class TestEmailDuplicado:
    def test_bate_com_o_indice_de_email(self):
        assert _email_duplicado(_ErroFake(_INDICE_EMAIL_UNICO)) is True

    def test_outra_constraint_nao_bate(self):
        assert _email_duplicado(_ErroFake("usuarios_usuario_key")) is False

    def test_erro_sem_diag_nao_bate(self):
        assert _email_duplicado(Exception("erro genérico")) is False
