from types import SimpleNamespace

from agente_oracle.agent.core import conteudo_do_resultado, mcp_url, resposta_json_como_dict


def test_mcp_url_monta_endpoint_streamable_http():
    assert mcp_url("127.0.0.1", 8000) == "http://127.0.0.1:8000/mcp"


def test_conteudo_do_resultado_junta_blocos_de_texto():
    resultado = SimpleNamespace(content=[SimpleNamespace(text="parte 1"), SimpleNamespace(text="parte 2")])
    assert conteudo_do_resultado(resultado) == "parte 1\nparte 2"


def test_conteudo_do_resultado_ignora_blocos_sem_texto():
    resultado = SimpleNamespace(content=[SimpleNamespace(text="só esse")])
    assert conteudo_do_resultado(resultado) == "só esse"


def test_conteudo_do_resultado_cai_no_str_quando_nao_ha_texto():
    resultado = SimpleNamespace(content=[])
    assert conteudo_do_resultado(resultado) == str(resultado)


class TestRespostaJsonComoDict:
    def test_objeto_valido_devolve_o_proprio_dict(self):
        assert resposta_json_como_dict('{"a": 1}') == {"a": 1}

    def test_none_devolve_dict_vazio(self):
        assert resposta_json_como_dict(None) == {}

    def test_string_vazia_devolve_dict_vazio(self):
        assert resposta_json_como_dict("") == {}

    def test_json_nao_valido_devolve_dict_vazio(self):
        assert resposta_json_como_dict("isso não é json") == {}

    def test_null_devolve_dict_vazio(self):
        assert resposta_json_como_dict("null") == {}

    def test_lista_devolve_dict_vazio(self):
        assert resposta_json_como_dict("[]") == {}

    def test_booleano_devolve_dict_vazio(self):
        assert resposta_json_como_dict("false") == {}
