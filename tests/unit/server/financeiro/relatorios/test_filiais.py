from agente_oracle.server.financeiro.relatorios.filiais import _filiais_visiveis


class TestFiliaisVisiveis:
    def test_sem_bloqueio_devolve_tudo(self):
        filiais = [{"codigo": "0101", "nome": "Matriz"}, {"codigo": "0102", "nome": "Filial 2"}]
        assert _filiais_visiveis(filiais, set()) == filiais

    def test_filial_bloqueada_some_da_lista(self):
        filiais = [{"codigo": "0101", "nome": "Matriz"}, {"codigo": "0102", "nome": "Filial 2"}]
        assert _filiais_visiveis(filiais, {"0102"}) == [{"codigo": "0101", "nome": "Matriz"}]

    def test_todas_bloqueadas_devolve_lista_vazia(self):
        filiais = [{"codigo": "0101", "nome": "Matriz"}]
        assert _filiais_visiveis(filiais, {"0101"}) == []
