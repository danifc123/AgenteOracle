import pytest

from agente_oracle.agent.rh.embeddings import AnaliseIndisponivel, gerar_embedding
from agente_oracle.tools.ia.cliente_openai_compativel import EmbeddingNaoSuportado


class _EmbedRespostaFake:
    def __init__(self, embedding: list[float]):
        self.embeddings = [embedding]


class _ClienteFake:
    def __init__(self, levantar: Exception | None = None, embedding: list[float] | None = None):
        self._levantar = levantar
        self._embedding = embedding or [1.0, 0.0]

    async def embed(self, **_kwargs):
        if self._levantar:
            raise self._levantar
        return _EmbedRespostaFake(self._embedding)


class TestGerarEmbedding:
    async def test_devolve_o_vetor_em_caso_de_sucesso(self):
        cliente = _ClienteFake(embedding=[0.1, 0.2, 0.3])

        vetor = await gerar_embedding(cliente, "modelo-embed", "texto qualquer")

        assert vetor == [0.1, 0.2, 0.3]

    async def test_provedor_sem_suporte_a_embedding_cita_o_provedor(self):
        cliente = _ClienteFake(levantar=EmbeddingNaoSuportado("sem embedding nesse provedor"))

        with pytest.raises(AnaliseIndisponivel, match="provedor de IA"):
            await gerar_embedding(cliente, "modelo-embed", "texto qualquer")

    async def test_falha_generica_mantem_a_mensagem_de_sempre(self):
        cliente = _ClienteFake(levantar=ConnectionError("Ollama fora do ar"))

        with pytest.raises(AnaliseIndisponivel, match="baixado no Ollama"):
            await gerar_embedding(cliente, "modelo-embed", "texto qualquer")
