from agente_oracle.tools.financeiro.localizacao_cliente import _texto_busca


class TestTextoBusca:
    def test_cidade_e_bairro_junta_os_dois(self):
        assert _texto_busca("Cabo Frio", "Jardim Excelsior") == "Jardim Excelsior, Cabo Frio"

    def test_so_cidade_devolve_a_cidade(self):
        assert _texto_busca("Cabo Frio", None) == "Cabo Frio"

    def test_sem_cidade_devolve_none_mesmo_com_bairro(self):
        assert _texto_busca(None, "Jardim Excelsior") is None

    def test_sem_cidade_e_sem_bairro_devolve_none(self):
        assert _texto_busca(None, None) is None
