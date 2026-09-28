import pytest

from agente_oracle.tools.ia.cliente_oci_nativo import ChatNaoSuportado, ClienteOciNativo


class _RespostaEmbedFake:
    def __init__(self, data):
        self.data = data


class _ClienteOciFake:
    def __init__(self, resposta_data=None, erro: Exception | None = None):
        self._resposta_data = resposta_data
        self._erro = erro
        self.chamadas: list[object] = []

    def embed_text(self, detalhes):
        self.chamadas.append(detalhes)
        if self._erro:
            raise self._erro
        return _RespostaEmbedFake(self._resposta_data)


class TestEmbed:
    async def test_manda_o_texto_o_modelo_e_o_compartment_certos(self):
        cliente_fake = _ClienteOciFake(resposta_data=[[0.1, 0.2]])
        cliente = ClienteOciNativo(cliente_fake, "ocid1.compartment.oc1..xyz")

        await cliente.embed(input="ola mundo", model="cohere.embed-v4.0")

        detalhes = cliente_fake.chamadas[0]
        assert detalhes.inputs == ["ola mundo"]
        assert detalhes.compartment_id == "ocid1.compartment.oc1..xyz"
        assert detalhes.truncate == "NONE"
        assert detalhes.serving_mode.model_id == "cohere.embed-v4.0"

    async def test_lista_de_textos_e_enviada_como_veio(self):
        cliente_fake = _ClienteOciFake(resposta_data=[[0.1], [0.2]])
        cliente = ClienteOciNativo(cliente_fake, "ocid1.compartment.oc1..xyz")

        await cliente.embed(input=["um", "dois"], model="cohere.embed-v4.0")

        assert cliente_fake.chamadas[0].inputs == ["um", "dois"]

    async def test_devolve_os_dados_da_resposta(self):
        cliente_fake = _ClienteOciFake(resposta_data=[[0.1, 0.2, 0.3]])
        cliente = ClienteOciNativo(cliente_fake, "ocid1.compartment.oc1..xyz")

        resultado = await cliente.embed(input="ola", model="cohere.embed-v4.0")

        assert resultado == [[0.1, 0.2, 0.3]]

    async def test_erro_do_sdk_sobe_pra_quem_chamou(self):
        cliente_fake = _ClienteOciFake(erro=RuntimeError("chave inválida"))
        cliente = ClienteOciNativo(cliente_fake, "ocid1.compartment.oc1..xyz")

        with pytest.raises(RuntimeError, match="chave inválida"):
            await cliente.embed(input="ola", model="cohere.embed-v4.0")


class TestChat:
    async def test_chat_sempre_levanta_chat_nao_suportado(self):
        cliente = ClienteOciNativo(_ClienteOciFake(), "ocid1.compartment.oc1..xyz")

        with pytest.raises(ChatNaoSuportado):
            await cliente.chat(messages=[{"role": "user", "content": "oi"}])
