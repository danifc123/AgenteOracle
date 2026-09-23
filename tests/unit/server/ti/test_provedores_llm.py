from datetime import UTC, datetime
from decimal import Decimal

from agente_oracle.server.ti import provedores_llm as mod
from agente_oracle.tools.ia.provedores_llm import ProvedorLLM, ProvedorLlmJaExiste


def _provedor_llm(**overrides) -> ProvedorLLM:
    campos = {
        "id": 1,
        "nome": "OCI Generative AI — gpt-oss-120b",
        "tipo_conexao": "openai_compativel",
        "base_url": "https://inference.generativeai.sa-saopaulo-1.oci.oraclecloud.com/openai/v1",
        "api_key": "sk-segredo",
        "projeto_id": "ocid1.generativeaiproject.oc1...",
        "modelo": "openai.gpt-oss-120b",
        "estilo_api": "responses",
        "preco_entrada_por_1k": Decimal("0.01"),
        "preco_saida_por_1k": Decimal("0.02"),
        "moeda": "R$",
        "criado_em": datetime(2026, 9, 23, tzinfo=UTC),
    }
    campos.update(overrides)
    return ProvedorLLM(**campos)


class TestPrecoValido:
    def test_numero_positivo_e_aceito(self):
        assert mod._preco_valido(1.5) == Decimal("1.5")

    def test_zero_e_aceito(self):
        assert mod._preco_valido(0) == Decimal("0")

    def test_string_numerica_e_aceita(self):
        assert mod._preco_valido("2.5") == Decimal("2.5")

    def test_negativo_e_rejeitado(self):
        assert mod._preco_valido(-0.01) is None

    def test_bool_e_rejeitado(self):
        # `True` é `int` em Python — sem checagem explícita viraria 1.
        assert mod._preco_valido(True) is None

    def test_nao_numerico_e_rejeitado(self):
        assert mod._preco_valido("abc") is None

    def test_lista_e_rejeitada(self):
        assert mod._preco_valido([1]) is None


class TestProvedorParaJson:
    def test_nunca_inclui_a_api_key_crua(self):
        corpo = mod._provedor_para_json(_provedor_llm(api_key="sk-super-secreto"), id_ativo=None)

        assert "api_key" not in corpo
        assert corpo["api_key_configurada"] is True

    def test_sem_api_key_configurada_e_false(self):
        corpo = mod._provedor_para_json(_provedor_llm(api_key=""), id_ativo=None)

        assert corpo["api_key_configurada"] is False

    def test_marca_ativo_quando_o_id_bate(self):
        corpo = mod._provedor_para_json(_provedor_llm(id=7), id_ativo=7)

        assert corpo["ativo"] is True

    def test_nao_marca_ativo_quando_o_id_nao_bate(self):
        corpo = mod._provedor_para_json(_provedor_llm(id=7), id_ativo=8)

        assert corpo["ativo"] is False

    def test_precos_viram_float(self):
        corpo = mod._provedor_para_json(
            _provedor_llm(preco_entrada_por_1k=Decimal("0.01"), preco_saida_por_1k=Decimal("0.02")), id_ativo=None
        )

        assert corpo["preco_entrada_por_1k"] == 0.01
        assert corpo["preco_saida_por_1k"] == 0.02


class TestValidarCamposComuns:
    def test_criacao_sem_nome_e_rejeitada(self):
        assert mod._validar_campos_comuns({"base_url": "x", "modelo": "y"}, exigir_obrigatorios=True) is not None

    def test_criacao_com_obrigatorios_preenchidos_passa(self):
        corpo = {"nome": "n", "base_url": "x", "modelo": "y"}
        assert mod._validar_campos_comuns(corpo, exigir_obrigatorios=True) is None

    def test_edicao_sem_obrigatorios_nao_exige_nada(self):
        assert mod._validar_campos_comuns({}, exigir_obrigatorios=False) is None

    def test_tipo_conexao_invalido_e_rejeitado(self):
        corpo = {"nome": "n", "base_url": "x", "modelo": "y", "tipo_conexao": "azure"}
        assert mod._validar_campos_comuns(corpo, exigir_obrigatorios=True) is not None

    def test_estilo_api_invalido_e_rejeitado(self):
        corpo = {"nome": "n", "base_url": "x", "modelo": "y", "estilo_api": "outro"}
        assert mod._validar_campos_comuns(corpo, exigir_obrigatorios=True) is not None

    def test_preco_negativo_e_rejeitado(self):
        corpo = {"nome": "n", "base_url": "x", "modelo": "y", "preco_entrada_por_1k": -1}
        assert mod._validar_campos_comuns(corpo, exigir_obrigatorios=True) is not None


class TestCriar:
    def test_corpo_invalido_devolve_400_sem_chamar_o_cadastro(self, monkeypatch):
        chamou = []
        monkeypatch.setattr(mod.provedores_llm, "criar", lambda **_kw: chamou.append(True))

        resposta = mod._criar({"base_url": "x", "modelo": "y"})  # sem nome

        assert resposta.status_code == 400
        assert chamou == []

    def test_corpo_valido_cria_e_devolve_201(self, monkeypatch):
        monkeypatch.setattr(mod.provedores_llm, "criar", lambda **_kw: _provedor_llm())
        monkeypatch.setattr(mod.configuracoes_provedor, "provedor_llm_ativo_id", lambda: None)

        resposta = mod._criar({"nome": "n", "base_url": "x", "modelo": "y"})

        assert resposta.status_code == 201

    def test_nome_duplicado_devolve_400(self, monkeypatch):
        def _levanta(**_kw):
            raise ProvedorLlmJaExiste('Já existe um provedor cadastrado com o nome "n".')

        monkeypatch.setattr(mod.provedores_llm, "criar", _levanta)

        resposta = mod._criar({"nome": "n", "base_url": "x", "modelo": "y"})

        assert resposta.status_code == 400


class TestAtualizar:
    def test_id_nao_numerico_devolve_404(self, monkeypatch):
        resposta = mod._atualizar("abc", {"nome": "n"})

        assert resposta.status_code == 404

    def test_id_inexistente_devolve_404(self, monkeypatch):
        monkeypatch.setattr(mod.provedores_llm, "atualizar", lambda *_a, **_kw: None)

        resposta = mod._atualizar("999", {"nome": "n"})

        assert resposta.status_code == 404

    def test_edicao_valida_devolve_200(self, monkeypatch):
        monkeypatch.setattr(mod.provedores_llm, "atualizar", lambda *_a, **_kw: _provedor_llm())
        monkeypatch.setattr(mod.configuracoes_provedor, "provedor_llm_ativo_id", lambda: None)

        resposta = mod._atualizar("1", {"nome": "Novo nome"})

        assert resposta.status_code == 200

    def test_omitir_api_key_nao_manda_o_campo_pro_cadastro(self, monkeypatch):
        campos_recebidos = {}

        def _atualizar_fake(id_provedor, **campos):
            campos_recebidos.update(campos)
            return _provedor_llm()

        monkeypatch.setattr(mod.provedores_llm, "atualizar", _atualizar_fake)
        monkeypatch.setattr(mod.configuracoes_provedor, "provedor_llm_ativo_id", lambda: None)

        mod._atualizar("1", {"nome": "Novo nome"})

        assert "api_key" not in campos_recebidos

    def test_mandar_api_key_nova_repassa_ela(self, monkeypatch):
        campos_recebidos = {}

        def _atualizar_fake(id_provedor, **campos):
            campos_recebidos.update(campos)
            return _provedor_llm()

        monkeypatch.setattr(mod.provedores_llm, "atualizar", _atualizar_fake)
        monkeypatch.setattr(mod.configuracoes_provedor, "provedor_llm_ativo_id", lambda: None)

        mod._atualizar("1", {"api_key": "chave-nova"})

        assert campos_recebidos["api_key"] == "chave-nova"


class TestRemover:
    def test_id_nao_numerico_devolve_404(self):
        assert mod._remover("abc").status_code == 404

    def test_nao_encontrado_devolve_404(self, monkeypatch):
        monkeypatch.setattr(mod.provedores_llm, "remover", lambda _id: False)

        assert mod._remover("999").status_code == 404

    def test_remover_o_ativo_limpa_o_ponteiro(self, monkeypatch):
        limpou = []
        monkeypatch.setattr(mod.provedores_llm, "remover", lambda _id: True)
        monkeypatch.setattr(mod.configuracoes_provedor, "provedor_llm_ativo_id", lambda: 1)
        monkeypatch.setattr(mod.configuracoes_provedor, "definir_provedor_llm_ativo_id", lambda v: limpou.append(v))

        resposta = mod._remover("1")

        assert resposta.status_code == 200
        assert limpou == [None]

    def test_remover_outro_provedor_nao_mexe_no_ponteiro(self, monkeypatch):
        limpou = []
        monkeypatch.setattr(mod.provedores_llm, "remover", lambda _id: True)
        monkeypatch.setattr(mod.configuracoes_provedor, "provedor_llm_ativo_id", lambda: 2)
        monkeypatch.setattr(mod.configuracoes_provedor, "definir_provedor_llm_ativo_id", lambda v: limpou.append(v))

        mod._remover("1")

        assert limpou == []


class TestAtivar:
    def test_id_nao_numerico_devolve_404(self):
        assert mod._ativar("abc").status_code == 404

    def test_provedor_inexistente_devolve_404(self, monkeypatch):
        monkeypatch.setattr(mod.provedores_llm, "buscar", lambda _id: None)

        assert mod._ativar("999").status_code == 404

    def test_provedor_existente_define_o_ponteiro_e_devolve_a_lista(self, monkeypatch):
        definidos = []
        monkeypatch.setattr(mod.provedores_llm, "buscar", lambda _id: _provedor_llm(id=1))
        monkeypatch.setattr(mod.configuracoes_provedor, "definir_provedor_llm_ativo_id", lambda v: definidos.append(v))
        monkeypatch.setattr(mod.provedores_llm, "listar", lambda: [_provedor_llm(id=1)])
        monkeypatch.setattr(mod.configuracoes_provedor, "provedor_llm_ativo_id", lambda: 1)

        resposta = mod._ativar("1")

        assert definidos == [1]
        assert resposta.status_code == 200
