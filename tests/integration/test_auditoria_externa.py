"""Auditoria de chamada de IA externa contra o Postgres real."""

import pytest

from agente_oracle.db.connection import get_postgres_connection
from agente_oracle.tools.ia import auditoria_externa

pytestmark = pytest.mark.integration

_DOMINIO_TESTE = "__teste__"


def _apagar_dados_de_teste() -> None:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM auditoria_ia_externa WHERE dominio = :dominio", dominio=_DOMINIO_TESTE)


@pytest.fixture(autouse=True)
def _isolar_dados_de_teste():
    auditoria_externa.contagem_hoje(_DOMINIO_TESTE)  # cria a tabela, se ainda não existir
    _apagar_dados_de_teste()
    yield
    _apagar_dados_de_teste()


class TestAuditoriaExterna:
    def test_registrar_e_contar_no_mesmo_dia(self):
        assert auditoria_externa.contagem_hoje(_DOMINIO_TESTE) == 0

        auditoria_externa.registrar(_DOMINIO_TESTE, "http://127.0.0.1:11434", "primeiro texto")
        auditoria_externa.registrar(_DOMINIO_TESTE, "http://127.0.0.1:11434", "segundo texto")

        assert auditoria_externa.contagem_hoje(_DOMINIO_TESTE) == 2

    def test_contagem_nao_mistura_dominios_diferentes(self):
        auditoria_externa.registrar(_DOMINIO_TESTE, "http://127.0.0.1:11434", "texto do domínio de teste")
        auditoria_externa.registrar("ti", "http://127.0.0.1:11434", "texto de outro domínio")

        assert auditoria_externa.contagem_hoje(_DOMINIO_TESTE) == 1

    def test_hash_gravado_nao_e_o_texto_puro(self):
        auditoria_externa.registrar(_DOMINIO_TESTE, "http://127.0.0.1:11434", "CPF 123.456.789-00")

        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT hash_conteudo, tamanho_caracteres FROM auditoria_ia_externa WHERE dominio = :dominio",
                dominio=_DOMINIO_TESTE,
            )
            hash_conteudo, tamanho = cursor.fetchone()

        assert "123.456.789-00" not in hash_conteudo
        assert tamanho == len("CPF 123.456.789-00")
