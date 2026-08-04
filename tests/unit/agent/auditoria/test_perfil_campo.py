import pytest

from agente_oracle.agent.auditoria.perfil_campo import PerfilCampo, campo_seguro_para_auditoria


class TestCampoSeguroParaAuditoria:
    @pytest.mark.parametrize(
        "campo",
        ["filial", "estado", "tipo_pessoa", "cnpj_cpf", "situacao", "descricao"],
    )
    def test_campos_normais_sao_seguros(self, campo: str) -> None:
        assert campo_seguro_para_auditoria(campo) is True

    @pytest.mark.parametrize(
        "campo",
        [
            "senha",
            "senha_hash",
            "password",
            "passwd",
            "hash_documento",
            "token_acesso",
            "api_key",
            "secret",
            "segredo_cliente",
            "chave_criptografia",
            "pin_cartao",
            "cvv",
            "SENHA",
            "Token",
        ],
    )
    def test_campos_sensiveis_sao_rejeitados(self, campo: str) -> None:
        assert campo_seguro_para_auditoria(campo) is False


class TestPerfilCampoValidaCampo:
    def test_criacao_com_campo_seguro_funciona(self) -> None:
        perfil = PerfilCampo(modulo="financeiro", view="vw_clientes", campo="estado", valores=(("SP", 10),))
        assert perfil.campo == "estado"

    def test_criacao_com_campo_sensivel_levanta_erro(self) -> None:
        with pytest.raises(ValueError, match="credencial/hash"):
            PerfilCampo(modulo="financeiro", view="vw_usuarios", campo="senha_hash", valores=(("x", 1),))
