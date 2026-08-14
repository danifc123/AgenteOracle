from agente_oracle.tools.rh.candidatos import _id_duplicata, _nome_normalizado, _sem_duplicatas


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


class TestIdDuplicata:
    def test_nome_igual_e_embedding_parecido_devolve_id_existente(self):
        candidatos_existentes = [{"id": 1, "nome": "Ana Souza", "embedding": [1.0, 0.0, 0.0]}]
        assert _id_duplicata("Ana Souza", [1.0, 0.0, 0.0], candidatos_existentes) == 1

    def test_nome_igual_e_embedding_diferente_devolve_none(self):
        candidatos_existentes = [{"id": 1, "nome": "Ana Souza", "embedding": [1.0, 0.0, 0.0]}]
        assert _id_duplicata("Ana Souza", [0.0, 1.0, 0.0], candidatos_existentes) is None

    def test_nome_diferente_e_embedding_identico_devolve_none(self):
        candidatos_existentes = [{"id": 1, "nome": "Bruno Lima", "embedding": [1.0, 0.0, 0.0]}]
        assert _id_duplicata("Ana Souza", [1.0, 0.0, 0.0], candidatos_existentes) is None

    def test_lista_de_existentes_vazia_devolve_none(self):
        assert _id_duplicata("Ana Souza", [1.0, 0.0, 0.0], []) is None

    def test_bate_com_candidato_descartado_ou_contratado_tambem(self):
        """_id_duplicata não filtra por status — quem chama (criar_candidato)
        decide se busca entre todo mundo ou só um subconjunto; a função só
        compara o que recebeu."""
        candidatos_existentes = [{"id": 7, "nome": "Ana Souza", "embedding": [1.0, 0.0, 0.0]}]
        assert _id_duplicata("Ana Souza", [1.0, 0.0, 0.0], candidatos_existentes) == 7
