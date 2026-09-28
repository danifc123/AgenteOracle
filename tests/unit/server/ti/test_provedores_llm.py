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
        "capacidades": ["chat"],
        "credenciais_extra": None,
        "credencial_atualizada_em": datetime(2026, 9, 23, tzinfo=UTC),
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
    def test_inclui_credencial_atualizada_em(self):
        corpo = mod._provedor_para_json(
            _provedor_llm(credencial_atualizada_em=datetime(2026, 6, 1, tzinfo=UTC)), id_ativo=None
        )

        assert corpo["credencial_atualizada_em"] == "2026-06-01T00:00:00+00:00"

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

    def test_inclui_capacidades(self):
        corpo = mod._provedor_para_json(_provedor_llm(capacidades=["chat", "embedding"]), id_ativo=None)

        assert corpo["capacidades"] == ["chat", "embedding"]

    def test_nunca_inclui_credenciais_extra_cruas(self):
        corpo = mod._provedor_para_json(
            _provedor_llm(credenciais_extra={"chave_privada": "segredo"}), id_ativo=None
        )

        assert "credenciais_extra" not in corpo
        assert corpo["credenciais_configuradas"] is True

    def test_sem_credenciais_extra_e_false(self):
        corpo = mod._provedor_para_json(_provedor_llm(credenciais_extra=None), id_ativo=None)

        assert corpo["credenciais_configuradas"] is False


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

    def test_capacidades_invalidas_sao_rejeitadas(self):
        corpo = {"nome": "n", "base_url": "x", "modelo": "y", "capacidades": ["voo"]}
        assert mod._validar_campos_comuns(corpo, exigir_obrigatorios=True) is not None

    def test_capacidades_validas_passam(self):
        corpo = {"nome": "n", "base_url": "x", "modelo": "y", "capacidades": ["chat", "embedding"]}
        assert mod._validar_campos_comuns(corpo, exigir_obrigatorios=True) is None

    def test_oci_nativo_nao_exige_base_url(self):
        corpo = {
            "nome": "n",
            "modelo": "cohere.embed-v4.0",
            "tipo_conexao": "oci_nativo",
            "credenciais_extra": {
                "user_ocid": "u",
                "fingerprint": "f",
                "tenancy_ocid": "t",
                "regiao": "sa-saopaulo-1",
                "compartment_id": "c",
                "chave_privada": "k",
            },
        }
        assert mod._validar_campos_comuns(corpo, exigir_obrigatorios=True) is None

    def test_oci_nativo_sem_credenciais_extra_e_rejeitado(self):
        corpo = {"nome": "n", "modelo": "m", "tipo_conexao": "oci_nativo"}
        assert mod._validar_campos_comuns(corpo, exigir_obrigatorios=True) is not None

    def test_oci_nativo_com_credencial_faltando_e_rejeitado(self):
        corpo = {
            "nome": "n",
            "modelo": "m",
            "tipo_conexao": "oci_nativo",
            "credenciais_extra": {"user_ocid": "u"},  # faltam os outros campos
        }
        assert mod._validar_campos_comuns(corpo, exigir_obrigatorios=True) is not None

    def test_oci_nativo_na_edicao_sem_credenciais_nao_exige_nada(self):
        # Edição (exigir_obrigatorios=False) não força recadastrar credencial.
        corpo = {"tipo_conexao": "oci_nativo", "nome": "novo nome"}
        assert mod._validar_campos_comuns(corpo, exigir_obrigatorios=False) is None


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

    def test_capacidades_omitida_usa_padrao_chat(self, monkeypatch):
        campos_recebidos = {}

        def _criar_fake(**campos):
            campos_recebidos.update(campos)
            return _provedor_llm()

        monkeypatch.setattr(mod.provedores_llm, "criar", _criar_fake)
        monkeypatch.setattr(mod.configuracoes_provedor, "provedor_llm_ativo_id", lambda: None)

        mod._criar({"nome": "n", "base_url": "x", "modelo": "y"})

        assert campos_recebidos["capacidades"] == ["chat"]

    def test_oci_nativo_calcula_base_url_pela_regiao_e_repassa_credenciais(self, monkeypatch):
        campos_recebidos = {}

        def _criar_fake(**campos):
            campos_recebidos.update(campos)
            return _provedor_llm()

        monkeypatch.setattr(mod.provedores_llm, "criar", _criar_fake)
        monkeypatch.setattr(mod.configuracoes_provedor, "provedor_llm_ativo_id", lambda: None)
        credenciais = {
            "user_ocid": "u",
            "fingerprint": "f",
            "tenancy_ocid": "t",
            "regiao": "sa-saopaulo-1",
            "compartment_id": "c",
            "chave_privada": "k",
        }

        mod._criar(
            {
                "nome": "n",
                "modelo": "cohere.embed-v4.0",
                "tipo_conexao": "oci_nativo",
                "capacidades": ["embedding"],
                "credenciais_extra": credenciais,
            }
        )

        assert campos_recebidos["base_url"] == "https://inference.generativeai.sa-saopaulo-1.oci.oraclecloud.com"
        assert campos_recebidos["credenciais_extra"] == credenciais

    def test_credenciais_extra_ignorada_pra_tipo_que_nao_e_oci_nativo(self, monkeypatch):
        campos_recebidos = {}

        def _criar_fake(**campos):
            campos_recebidos.update(campos)
            return _provedor_llm()

        monkeypatch.setattr(mod.provedores_llm, "criar", _criar_fake)
        monkeypatch.setattr(mod.configuracoes_provedor, "provedor_llm_ativo_id", lambda: None)

        mod._criar(
            {
                "nome": "n",
                "base_url": "x",
                "modelo": "y",
                "credenciais_extra": {"algo": "que nao deveria ir"},
            }
        )

        assert campos_recebidos["credenciais_extra"] is None


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


class TestDesativar:
    def test_limpa_o_ponteiro_e_devolve_a_lista(self, monkeypatch):
        definidos = []
        monkeypatch.setattr(mod.configuracoes_provedor, "definir_provedor_llm_ativo_id", lambda v: definidos.append(v))
        monkeypatch.setattr(mod.provedores_llm, "listar", lambda: [_provedor_llm(id=1)])
        monkeypatch.setattr(mod.configuracoes_provedor, "provedor_llm_ativo_id", lambda: None)

        resposta = mod._desativar()

        assert definidos == [None]
        assert resposta.status_code == 200


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

    def test_provedor_sem_capacidade_de_chat_nao_pode_ser_ativado(self, monkeypatch):
        definidos = []
        monkeypatch.setattr(
            mod.provedores_llm, "buscar", lambda _id: _provedor_llm(id=1, capacidades=["embedding"])
        )
        monkeypatch.setattr(mod.configuracoes_provedor, "definir_provedor_llm_ativo_id", lambda v: definidos.append(v))

        resposta = mod._ativar("1")

        assert resposta.status_code == 400
        assert definidos == []

    def test_provedor_com_chat_e_embedding_pode_ser_ativado(self, monkeypatch):
        definidos = []
        monkeypatch.setattr(
            mod.provedores_llm, "buscar", lambda _id: _provedor_llm(id=1, capacidades=["chat", "embedding"])
        )
        monkeypatch.setattr(mod.configuracoes_provedor, "definir_provedor_llm_ativo_id", lambda v: definidos.append(v))
        monkeypatch.setattr(mod.provedores_llm, "listar", lambda: [])
        monkeypatch.setattr(mod.configuracoes_provedor, "provedor_llm_ativo_id", lambda: 1)

        resposta = mod._ativar("1")

        assert resposta.status_code == 200
        assert definidos == [1]


class TestTestar:
    async def test_id_nao_numerico_devolve_404(self):
        assert (await mod._testar("abc")).status_code == 404

    async def test_provedor_inexistente_devolve_404(self, monkeypatch):
        monkeypatch.setattr(mod.provedores_llm, "buscar", lambda _id: None)

        assert (await mod._testar("999")).status_code == 404

    async def test_capacidade_embedding_chama_embed_nao_chat(self, monkeypatch):
        provedor = _provedor_llm(capacidades=["embedding"], modelo="cohere.embed-v4.0")
        monkeypatch.setattr(mod.provedores_llm, "buscar", lambda _id: provedor)
        chamadas_embed = []
        chamadas_chat = []

        class _ClienteFake:
            async def embed(self, **kwargs):
                chamadas_embed.append(kwargs)

            async def chat(self, **kwargs):
                chamadas_chat.append(kwargs)

        monkeypatch.setattr(mod.cliente_protegido, "construir_cliente_llm", lambda _p: (_ClienteFake(), "host"))

        resposta = await mod._testar("1")

        assert resposta.status_code == 200
        assert len(chamadas_embed) == 1
        assert chamadas_embed[0]["model"] == "cohere.embed-v4.0"
        assert chamadas_chat == []

    async def test_capacidade_chat_chama_chat_nao_embed(self, monkeypatch):
        provedor = _provedor_llm(capacidades=["chat"])
        monkeypatch.setattr(mod.provedores_llm, "buscar", lambda _id: provedor)
        chamadas_embed = []
        chamadas_chat = []

        class _ClienteFake:
            async def embed(self, **kwargs):
                chamadas_embed.append(kwargs)

            async def chat(self, **kwargs):
                chamadas_chat.append(kwargs)

        monkeypatch.setattr(mod.cliente_protegido, "construir_cliente_llm", lambda _p: (_ClienteFake(), "host"))

        resposta = await mod._testar("1")

        assert resposta.status_code == 200
        assert len(chamadas_chat) == 1
        assert chamadas_embed == []

    async def test_falha_na_chamada_devolve_400_com_a_mensagem(self, monkeypatch):
        provedor = _provedor_llm(capacidades=["embedding"])
        monkeypatch.setattr(mod.provedores_llm, "buscar", lambda _id: provedor)

        class _ClienteQueFalha:
            async def embed(self, **kwargs):
                raise RuntimeError("chave inválida")

        monkeypatch.setattr(
            mod.cliente_protegido, "construir_cliente_llm", lambda _p: (_ClienteQueFalha(), "host")
        )

        resposta = await mod._testar("1")

        assert resposta.status_code == 400

    async def test_nao_mexe_no_ponteiro_de_ativo(self, monkeypatch):
        provedor = _provedor_llm(capacidades=["embedding"])
        monkeypatch.setattr(mod.provedores_llm, "buscar", lambda _id: provedor)

        class _ClienteFake:
            async def embed(self, **kwargs):
                return None

        monkeypatch.setattr(mod.cliente_protegido, "construir_cliente_llm", lambda _p: (_ClienteFake(), "host"))
        chamou_definir = []
        monkeypatch.setattr(
            mod.configuracoes_provedor, "definir_provedor_llm_ativo_id", lambda v: chamou_definir.append(v)
        )

        await mod._testar("1")

        assert chamou_definir == []
