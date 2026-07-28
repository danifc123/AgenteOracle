import psycopg

from agente_oracle.db.connection import eh_erro_coluna_invalida, eh_erro_valor_duplicado


def _erro_postgres(sqlstate: str) -> psycopg.Error:
    erro = psycopg.Error("erro simulado")
    erro.sqlstate = sqlstate
    return erro


class TestEhErroColunaInvalida:
    def test_postgres_sqlstate_42703(self):
        assert eh_erro_coluna_invalida(_erro_postgres("42703")) is True

    def test_postgres_outro_sqlstate(self):
        assert eh_erro_coluna_invalida(_erro_postgres("23505")) is False

    def test_fallback_oracle_pela_mensagem(self):
        assert eh_erro_coluna_invalida(ValueError("ORA-00904: coluna inválida")) is True

    def test_fallback_oracle_mensagem_sem_o_codigo(self):
        assert eh_erro_coluna_invalida(ValueError("qualquer outro erro")) is False


class TestEhErroValorDuplicado:
    def test_postgres_sqlstate_23505(self):
        assert eh_erro_valor_duplicado(_erro_postgres("23505")) is True

    def test_postgres_outro_sqlstate(self):
        assert eh_erro_valor_duplicado(_erro_postgres("42703")) is False

    def test_fallback_oracle_pela_mensagem(self):
        assert eh_erro_valor_duplicado(ValueError("ORA-00001: unique constraint violated")) is True

    def test_fallback_oracle_mensagem_sem_o_codigo(self):
        assert eh_erro_valor_duplicado(ValueError("qualquer outro erro")) is False
