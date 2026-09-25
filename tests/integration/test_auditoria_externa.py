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


def _registrar(dominio: str, texto: str) -> None:
    auditoria_externa.registrar(
        dominio, "http://127.0.0.1:11434", texto, "ollama", "modelo-teste", 10, 5, None, "usuario-teste"
    )


class TestAuditoriaExterna:
    def test_registrar_e_contar_no_mesmo_dia(self):
        assert auditoria_externa.contagem_hoje(_DOMINIO_TESTE) == 0

        _registrar(_DOMINIO_TESTE, "primeiro texto")
        _registrar(_DOMINIO_TESTE, "segundo texto")

        assert auditoria_externa.contagem_hoje(_DOMINIO_TESTE) == 2

    def test_contagem_nao_mistura_dominios_diferentes(self):
        _registrar(_DOMINIO_TESTE, "texto do domínio de teste")
        _registrar("ti", "texto de outro domínio")

        assert auditoria_externa.contagem_hoje(_DOMINIO_TESTE) == 1

    def test_hash_gravado_nao_e_o_texto_puro(self):
        _registrar(_DOMINIO_TESTE, "CPF 123.456.789-00")

        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT hash_conteudo, tamanho_caracteres FROM auditoria_ia_externa WHERE dominio = :dominio",
                dominio=_DOMINIO_TESTE,
            )
            hash_conteudo, tamanho = cursor.fetchone()

        assert "123.456.789-00" not in hash_conteudo
        assert tamanho == len("CPF 123.456.789-00")

    def test_resumo_por_provedor_agrega_tokens(self):
        _registrar(_DOMINIO_TESTE, "primeiro texto")
        _registrar(_DOMINIO_TESTE, "segundo texto")

        resumo = auditoria_externa.resumo_por_provedor(dias=1)

        linha = next(item for item in resumo if item.provedor == "ollama" and item.modelo == "modelo-teste")
        assert linha.chamadas >= 2
        assert linha.tokens_entrada_total >= 20
        assert linha.tokens_saida_total >= 10

    def test_resumo_por_usuario_agrega_tokens(self):
        _registrar(_DOMINIO_TESTE, "primeiro texto")
        _registrar(_DOMINIO_TESTE, "segundo texto")

        resumo = auditoria_externa.resumo_por_usuario(dias=1)

        linha = next(item for item in resumo if item.usuario_id == "usuario-teste")
        assert linha.chamadas >= 2
        assert linha.tokens_entrada_total >= 20
        assert linha.tokens_saida_total >= 10
