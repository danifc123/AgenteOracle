from agente_oracle.tools.rh.candidatos import _nome_normalizado, _sem_duplicatas


class TestNomeNormalizado:
    def test_ignora_caixa(self):
        assert _nome_normalizado("Ana Souza") == _nome_normalizado("ANA SOUZA")

    def test_ignora_acento(self):
        assert _nome_normalizado("Ana Souza") == _nome_normalizado("Ána Sôuza")

    def test_ignora_espaco_repetido_e_nas_pontas(self):
        assert _nome_normalizado("Ana Souza") == _nome_normalizado("  ana   souza  ")

    def test_nomes_diferentes_nao_colidem(self):
        assert _nome_normalizado("Ana Souza") != _nome_normalizado("Ana Silva")


class TestSemDuplicatas:
    def test_mantem_so_a_primeira_ocorrencia_do_nome_normalizado(self):
        candidatos = [
            {"id": 2, "nome": "ANA SOUZA"},
            {"id": 1, "nome": "Ana Souza"},
        ]
        assert _sem_duplicatas(candidatos) == [{"id": 2, "nome": "ANA SOUZA"}]

    def test_lista_sem_duplicata_passa_igual(self):
        candidatos = [{"id": 1, "nome": "Ana Souza"}, {"id": 2, "nome": "Bruno Lima"}]
        assert _sem_duplicatas(candidatos) == candidatos

    def test_lista_vazia_devolve_vazia(self):
        assert _sem_duplicatas([]) == []

    def test_nomes_parecidos_mas_diferentes_nao_colapsam(self):
        candidatos = [{"id": 1, "nome": "Ana Souza"}, {"id": 2, "nome": "Ana Souza Lima"}]
        assert _sem_duplicatas(candidatos) == candidatos
