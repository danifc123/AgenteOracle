from agente_oracle.tools.auth.papeis import (
    MODULOS_CONHECIDOS,
    eh_administrador,
    modulos_liberados,
    pode_atribuir_papel,
    sigla_modulo,
    sigla_usuario,
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


class TestSiglaModulo:
    def test_modulo_conhecido_usa_sigla_cadastrada(self):
        assert sigla_modulo("financeiro") == "FIN"
        assert sigla_modulo("estoque") == "EST"

    def test_modulo_sem_sigla_cadastrada_cai_no_fallback(self):
        assert sigla_modulo("recursos_humanos") == "REC"


class TestSiglaUsuario:
    def test_financeiro_usa_sigla_do_modulo(self):
        assert sigla_usuario(["financeiro"]) == "FIN"

    def test_estoque_usa_sigla_do_modulo(self):
        assert sigla_usuario(["estoque"]) == "EST"

    def test_desenvolvedor_usa_dev_em_vez_da_lista_de_modulos(self):
        assert sigla_usuario(["desenvolvedor"]) == "DEV"

    def test_sem_papel_valido_devolve_vazio(self):
        assert sigla_usuario(["papel_que_nao_existe"]) == ""
        assert sigla_usuario([]) == ""


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
