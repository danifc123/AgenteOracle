from agente_oracle.tools.ti.categorias import AREA_POR_CATEGORIA_ID, CATEGORIAS, CATEGORIAS_ATRIBUIVEIS


class TestAreaPorCategoriaId:
    def test_sem_id_duplicado(self):
        ids = [categoria.id for categoria in CATEGORIAS]
        assert len(ids) == len(set(ids))

    def test_cobre_todas_as_categorias(self):
        assert len(AREA_POR_CATEGORIA_ID) == len(CATEGORIAS)

    def test_resolve_area_de_categoria_conhecida(self):
        assert AREA_POR_CATEGORIA_ID[391] == "processos"


class TestCategoriasAtribuiveis:
    def test_exclui_no_pasta_conhecido(self):
        # id 173 = "Tecnologia da Informação > Meu Computador e Periféricos"
        # — só 1 nível abaixo da raiz, é pasta organizadora, não folha
        # selecionável de verdade num chamado do GLPI.
        assert 173 not in [categoria.id for categoria in CATEGORIAS_ATRIBUIVEIS]

    def test_inclui_folha_conhecida(self):
        # id 175 = ".../Hardware e Componentes > Solicitar novo equipamento..."
        assert 175 in [categoria.id for categoria in CATEGORIAS_ATRIBUIVEIS]

    def test_exclui_no_pasta_de_processos(self):
        assert 390 not in [categoria.id for categoria in CATEGORIAS_ATRIBUIVEIS]

    def test_inclui_folha_de_processos(self):
        assert 391 in [categoria.id for categoria in CATEGORIAS_ATRIBUIVEIS]
