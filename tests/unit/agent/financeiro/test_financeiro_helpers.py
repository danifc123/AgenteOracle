"""Testa só os helpers privados e puros de `agent/financeiro/financeiro.py` —
`responder()` em si é assíncrona e acoplada a Ollama/MCP, fora do escopo
desta primeira leva de testes unitários."""

from agente_oracle.agent.financeiro import financeiro as mod


class TestNormalizarValorMonetario:
    def test_formato_brasileiro(self):
        assert mod._normalizar_valor_monetario("1.234,56") == 1234.56

    def test_formato_americano(self):
        assert mod._normalizar_valor_monetario("1,234.56") == 1234.56

    def test_numero_inteiro_sem_separador(self):
        assert mod._normalizar_valor_monetario("100") == 100.0

    def test_string_nao_numerica_devolve_none(self):
        assert mod._normalizar_valor_monetario("abc") is None

    def test_ponto_como_separador_de_milhar_sem_decimal(self):
        # "1.234" sem vírgula em lugar nenhum é 1234 (milhar), nunca 1,234
        # (fração) — valor monetário não tem 3 casas decimais de verdade.
        assert mod._normalizar_valor_monetario("1.234") == 1234.0

    def test_ponto_como_separador_de_milhar_duplo(self):
        assert mod._normalizar_valor_monetario("12.345.678") == 12345678.0


class TestValoresMonetariosNoTexto:
    def test_extrai_varios_valores_do_texto(self):
        texto = "O título A vale R$ 1.234,56 e o título B vale R$ 10,00."
        assert mod._valores_monetarios_no_texto(texto) == {1234.56, 10.0}

    def test_texto_sem_valor_monetario_devolve_vazio(self):
        assert mod._valores_monetarios_no_texto("não há nenhum valor aqui") == set()


class TestValoresNumericosDoResultado:
    def test_inclui_valores_e_soma_por_coluna(self):
        conteudo = '{"dados": [{"valor": 10}, {"valor": 20}]}'
        assert mod._valores_numericos_do_resultado(conteudo) == {10.0, 20.0, 30.0}

    def test_json_invalido_devolve_vazio(self):
        assert mod._valores_numericos_do_resultado("isso não é json") == set()

    def test_sem_chave_dados_devolve_vazio(self):
        assert mod._valores_numericos_do_resultado('{"outracoisa": 1}') == set()

    def test_ignora_booleanos(self):
        conteudo = '{"dados": [{"ativo": true, "valor": 5}]}'
        assert mod._valores_numericos_do_resultado(conteudo) == {5.0}


class TestLinhasRetornadas:
    def test_conta_linhas_de_dados(self):
        assert mod._linhas_retornadas('{"dados": [1, 2, 3]}') == 3

    def test_sem_chave_dados_devolve_none(self):
        assert mod._linhas_retornadas('{"outracoisa": 1}') is None

    def test_string_nao_json_devolve_none(self):
        assert mod._linhas_retornadas("não é json") is None


class TestRespostaSeguraGenerica:
    def test_usa_titulo_do_ultimo_evento_com_titulo(self):
        eventos = [
            {"argumentos": {}},
            {"argumentos": {"titulo": "Relatório de Vendas"}},
        ]
        resultado = mod._resposta_segura_generica(eventos)
        assert "Relatório de Vendas" in resultado

    def test_sem_nenhum_titulo_usa_mensagem_generica(self):
        eventos = [{"argumentos": {}}]
        resultado = mod._resposta_segura_generica(eventos)
        assert (
            resultado == "Consulta executada com sucesso — confira os dados retornados no relatório gerado."
        )
