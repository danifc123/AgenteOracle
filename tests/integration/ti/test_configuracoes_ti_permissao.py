"""Só desenvolvedor grava as configurações da Auditoria; qualquer usuário de TI lê."""

import time
import uuid

import pytest

from agente_oracle.db.connection import get_postgres_connection
from agente_oracle.tools.ti import configuracoes

pytestmark = pytest.mark.integration

_URL = "/api/ti/configuracoes"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _tirar_foto() -> tuple[list[str], dict[str, tuple]]:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        configuracoes.usar_ia_avaliacao_chamado()  # garante a tabela e as colunas atuais
        cursor.execute("SELECT * FROM ti_configuracoes")
        colunas = [descricao[0] for descricao in cursor.description]
        indice_chave = colunas.index("chave")
        return colunas, {linha[indice_chave]: linha for linha in cursor.fetchall()}


@pytest.fixture(autouse=True)
def _restaurar_configuracoes():
    colunas, antes = _tirar_foto()
    yield
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT chave FROM ti_configuracoes")
        for (chave,) in cursor.fetchall():
            if chave not in antes:
                cursor.execute("DELETE FROM ti_configuracoes WHERE chave = :chave", chave=chave)
        colunas_de_valor = [coluna for coluna in colunas if coluna != "chave"]
        atribuicoes = ", ".join(f"{coluna} = :v{i}" for i, coluna in enumerate(colunas_de_valor))
        for chave, linha in antes.items():
            valores = {f"v{i}": linha[colunas.index(coluna)] for i, coluna in enumerate(colunas_de_valor)}
            cursor.execute(
                f"UPDATE ti_configuracoes SET {atribuicoes} WHERE chave = :chave", chave=chave, **valores
            )


@pytest.fixture
def token_ti_admin(mcp_app):
    """Usuário de TI (acessa o módulo, é administrador dele) que NÃO é desenvolvedor."""
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login = f"teste_ti_cfg_{uuid.uuid4().hex[:12]}"
    senha = "SenhaDeTeste!123"
    criado = usuarios_tools.criar_usuario(login, senha, "Admin de TI (teste de configuração)", ["ti_admin"])
    try:
        resposta = mcp_app.post("/api/auth/login", json={"usuario": login, "senha": senha})
        assert resposta.status_code == 200
        yield resposta.json()["token"]
    finally:
        usuarios_tools.deletar_usuario(criado["id"])


class TestPercentualDeAmostragem:
    def test_usuario_de_ti_que_nao_e_desenvolvedor_nao_altera_o_percentual(self, mcp_app, token_ti_admin):
        resposta = mcp_app.patch(
            _URL, json={"percentual_amostragem_chamados": 37}, headers=_auth(token_ti_admin)
        )

        assert resposta.status_code == 403
        assert float(configuracoes.percentual_amostragem_chamados()) != 37  # nada foi gravado

    def test_desenvolvedor_altera_o_percentual(self, mcp_app, token_dev):
        resposta = mcp_app.patch(_URL, json={"percentual_amostragem_chamados": 20}, headers=_auth(token_dev))

        assert resposta.status_code == 200
        assert resposta.json()["percentual_amostragem_chamados"] == 20
        assert float(configuracoes.percentual_amostragem_chamados()) == 20

    def test_desenvolvedor_com_valor_invalido_recebe_400(self, mcp_app, token_dev):
        resposta = mcp_app.patch(_URL, json={"percentual_amostragem_chamados": 150}, headers=_auth(token_dev))

        assert resposta.status_code == 400


class TestDataDaUltimaMudancaDePercentual:
    """A referência que separa chamado "antigo" de "novo"."""

    def test_alterar_o_percentual_grava_a_data_da_mudanca(self, mcp_app, token_dev):
        antes = time.time()

        mcp_app.patch(_URL, json={"percentual_amostragem_chamados": 21}, headers=_auth(token_dev))

        alterado_em = configuracoes.percentual_alterado_em()
        assert alterado_em is not None
        assert alterado_em.timestamp() >= antes - 1

    def test_gravar_o_mesmo_percentual_de_novo_nao_move_a_data_de_referencia(self, mcp_app, token_dev):
        mcp_app.patch(_URL, json={"percentual_amostragem_chamados": 22}, headers=_auth(token_dev))
        primeira = configuracoes.percentual_alterado_em()
        time.sleep(1.1)

        mcp_app.patch(_URL, json={"percentual_amostragem_chamados": 22}, headers=_auth(token_dev))

        assert configuracoes.percentual_alterado_em() == primeira

    def test_mudar_para_outro_percentual_move_a_data_de_referencia(self, mcp_app, token_dev):
        mcp_app.patch(_URL, json={"percentual_amostragem_chamados": 22}, headers=_auth(token_dev))
        primeira = configuracoes.percentual_alterado_em()
        time.sleep(1.1)

        mcp_app.patch(_URL, json={"percentual_amostragem_chamados": 50}, headers=_auth(token_dev))

        assert configuracoes.percentual_alterado_em() > primeira


class TestLerChamadosAntigos:
    def test_usuario_de_ti_que_nao_e_desenvolvedor_nao_altera_a_flag(self, mcp_app, token_ti_admin):
        antes = configuracoes.ler_chamados_antigos()

        resposta = mcp_app.patch(
            _URL, json={"ler_chamados_antigos": not antes}, headers=_auth(token_ti_admin)
        )

        assert resposta.status_code == 403
        assert configuracoes.ler_chamados_antigos() is antes

    def test_desenvolvedor_liga_e_desliga_a_flag(self, mcp_app, token_dev):
        ligou = mcp_app.patch(_URL, json={"ler_chamados_antigos": True}, headers=_auth(token_dev))
        assert ligou.status_code == 200
        assert ligou.json()["ler_chamados_antigos"] is True
        assert configuracoes.ler_chamados_antigos() is True

        desligou = mcp_app.patch(_URL, json={"ler_chamados_antigos": False}, headers=_auth(token_dev))
        assert desligou.json()["ler_chamados_antigos"] is False
        assert configuracoes.ler_chamados_antigos() is False

    def test_valor_que_nao_e_booleano_recebe_400(self, mcp_app, token_dev):
        resposta = mcp_app.patch(_URL, json={"ler_chamados_antigos": "sim"}, headers=_auth(token_dev))

        assert resposta.status_code == 400

    def test_mexer_na_flag_nao_move_a_data_de_referencia_do_percentual(self, mcp_app, token_dev):
        mcp_app.patch(_URL, json={"percentual_amostragem_chamados": 23}, headers=_auth(token_dev))
        referencia = configuracoes.percentual_alterado_em()
        time.sleep(1.1)

        mcp_app.patch(_URL, json={"ler_chamados_antigos": True}, headers=_auth(token_dev))

        assert configuracoes.percentual_alterado_em() == referencia

    def test_a_flag_aparece_na_leitura_da_configuracao(self, mcp_app, token_dev):
        resposta = mcp_app.get(_URL, headers=_auth(token_dev))

        assert resposta.status_code == 200
        assert "ler_chamados_antigos" in resposta.json()


class TestUsarIaDaAvaliacao:
    def test_usuario_de_ti_que_nao_e_desenvolvedor_nao_altera_o_uso_de_ia(self, mcp_app, token_ti_admin):
        antes = configuracoes.usar_ia_avaliacao_chamado()

        resposta = mcp_app.patch(
            _URL, json={"usar_ia_avaliacao_chamado": not antes}, headers=_auth(token_ti_admin)
        )

        assert resposta.status_code == 403
        assert configuracoes.usar_ia_avaliacao_chamado() is antes

    def test_desenvolvedor_liga_e_desliga_o_uso_de_ia(self, mcp_app, token_dev):
        desligou = mcp_app.patch(_URL, json={"usar_ia_avaliacao_chamado": False}, headers=_auth(token_dev))
        assert desligou.status_code == 200
        assert desligou.json()["usar_ia_avaliacao_chamado"] is False
        assert configuracoes.usar_ia_avaliacao_chamado() is False

        ligou = mcp_app.patch(_URL, json={"usar_ia_avaliacao_chamado": True}, headers=_auth(token_dev))
        assert ligou.json()["usar_ia_avaliacao_chamado"] is True

    def test_pedido_misto_com_chave_restrita_e_recusado_inteiro(self, mcp_app, token_ti_admin):
        # Se qualquer chave do pedido é restrita a desenvolvedor, NADA é gravado.
        antes = configuracoes.usar_ia_avaliacao_chamado()

        resposta = mcp_app.patch(
            _URL,
            json={"usar_ia_avaliacao_chamado": not antes, "percentual_amostragem_chamados": 37},
            headers=_auth(token_ti_admin),
        )

        assert resposta.status_code == 403
        assert configuracoes.usar_ia_avaliacao_chamado() is antes
        assert float(configuracoes.percentual_amostragem_chamados()) != 37


class TestLeituraContinuaLiberadaParaTi:
    def test_usuario_de_ti_le_a_configuracao(self, mcp_app, token_ti_admin):
        resposta = mcp_app.get(_URL, headers=_auth(token_ti_admin))

        assert resposta.status_code == 200
        assert "usar_ia_avaliacao_chamado" in resposta.json()


class TestMetodoDaRota:
    def test_deveria_recusar_put_porque_a_atualizacao_parcial_e_patch(self, mcp_app, token_dev):
        resposta = mcp_app.put(_URL, json={"ler_chamados_antigos": True}, headers=_auth(token_dev))

        assert resposta.status_code == 405
