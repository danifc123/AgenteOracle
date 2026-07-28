from types import SimpleNamespace

from agente_oracle.agent.core import conteudo_do_resultado, mcp_url


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
