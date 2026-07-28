from agente_oracle.tools.auth.papeis import (
    MODULOS_CONHECIDOS,
    eh_administrador,
    modulos_liberados,
    pode_atribuir_papel,
    tem_acesso_modulo,
)


class TestTemAcessoModulo:
    def test_papel_com_o_modulo_libera(self):
        assert tem_acesso_modulo(["financeiro"], "financeiro") is True

    def test_papel_sem_o_modulo_nao_libera(self):
        assert tem_acesso_modulo(["financeiro"], "rh") is False

    def test_acesso_total_libera_qualquer_modulo(self):
        assert tem_acesso_modulo(["desenvolvedor"], "financeiro") is True
        assert tem_acesso_modulo(["desenvolvedor"], "qualquer_coisa_inventada") is True

    def test_slug_desconhecido_e_ignorado_sem_quebrar(self):
        assert tem_acesso_modulo(["papel_que_nao_existe"], "financeiro") is False

    def test_lista_vazia_nao_libera_nada(self):
        assert tem_acesso_modulo([], "financeiro") is False


class TestEhAdministrador:
    def test_financeiro_admin_e_administrador(self):
        assert eh_administrador(["financeiro_admin"]) is True

    def test_desenvolvedor_e_administrador(self):
        assert eh_administrador(["desenvolvedor"]) is True

    def test_financeiro_nao_e_administrador(self):
        assert eh_administrador(["financeiro"]) is False

    def test_lista_vazia_nao_e_administrador(self):
        assert eh_administrador([]) is False


class TestModulosLiberados:
    def test_desenvolvedor_libera_todos_os_modulos_conhecidos(self):
        assert modulos_liberados(["desenvolvedor"]) == list(MODULOS_CONHECIDOS)

    def test_financeiro_libera_so_financeiro(self):
        assert modulos_liberados(["financeiro"]) == ["financeiro"]

    def test_combinacao_de_papeis_faz_uniao_ordenada(self):
        assert modulos_liberados(["financeiro", "financeiro_admin"]) == ["financeiro"]

    def test_papel_invalido_e_ignorado(self):
        assert modulos_liberados(["papel_que_nao_existe"]) == []


class TestPodeAtribuirPapel:
    def test_nao_admin_nao_pode_atribuir_papel_de_acesso_total(self):
        assert pode_atribuir_papel(["financeiro"], "desenvolvedor") is False

    def test_desenvolvedor_pode_atribuir_desenvolvedor(self):
        assert pode_atribuir_papel(["desenvolvedor"], "desenvolvedor") is True

    def test_qualquer_um_pode_atribuir_papel_sem_acesso_total(self):
        assert pode_atribuir_papel(["financeiro"], "financeiro") is True
        assert pode_atribuir_papel([], "financeiro") is True

    def test_papel_alvo_inexistente_nao_pode_ser_atribuido(self):
        assert pode_atribuir_papel(["desenvolvedor"], "papel_que_nao_existe") is False
