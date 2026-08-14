import json

import pytest

from agente_oracle.agent.rh import busca_candidatos as mod
from agente_oracle.agent.rh.embeddings import AnaliseIndisponivel


class _RespostaFake:
    def __init__(self, conteudo: str | None):
        self.message = type("Mensagem", (), {"content": conteudo})()


class _EmbedRespostaFake:
    def __init__(self, embedding: list[float]):
        self.embeddings = [embedding]


class _OllamaClientFake:
    """`buscar_candidatos` usa `embed(...)` (retrieval) e `chat(...)`
    (generation) — um fake simples de cada já satisfaz as duas interfaces,
    sem precisar de um servidor Ollama de verdade."""

    def __init__(
        self,
        embedding: list[float] | None = None,
        conteudo_chat: str | None = None,
        levantar_embed: Exception | None = None,
        levantar_chat: Exception | None = None,
    ):
        self._embedding = embedding or [1.0, 0.0]
        self._conteudo_chat = conteudo_chat
        self._levantar_embed = levantar_embed
        self._levantar_chat = levantar_chat

    async def embed(self, **_kwargs):
        if self._levantar_embed:
            raise self._levantar_embed
        return _EmbedRespostaFake(self._embedding)

    async def chat(self, **_kwargs):
        if self._levantar_chat:
            raise self._levantar_chat
        return _RespostaFake(self._conteudo_chat)


def _candidato(
    id_: int, embedding: list[float], nome: str = "Candidato", perfil_estruturado: dict | None = None
) -> dict:
    return {
        "id": id_,
        "nome": nome,
        "resumo_perfil": "Resumo qualquer.",
        "perfil_estruturado": perfil_estruturado or {},
        "embedding": embedding,
    }


def _ranking_json(*resultados: dict) -> str:
    return json.dumps({"resultados": list(resultados)})


class TestBuscarCandidatos:
    async def test_resposta_valida_devolve_ranking_ordenado_por_posicao(self):
        candidatos = [_candidato(1, [1.0, 0.0], "Ana"), _candidato(2, [1.0, 0.0], "Bruno")]
        conteudo = _ranking_json(
            {"candidato_id": 2, "posicao": 1, "justificativa": "Melhor encaixe."},
            {"candidato_id": 1, "posicao": 2, "justificativa": "Encaixe razoável."},
        )
        cliente = _OllamaClientFake(embedding=[1.0, 0.0], conteudo_chat=conteudo)

        resultados = await mod.buscar_candidatos(
            cliente, "modelo-teste", "modelo-embed", "descrição", candidatos
        )

        assert [resultado.candidato_id for resultado in resultados] == [2, 1]
        assert resultados[0].nome == "Bruno"

    async def test_dados_estruturados_do_candidato_aparecem_no_resultado(self):
        candidatos = [
            _candidato(
                1,
                [1.0, 0.0],
                "Ana",
                perfil_estruturado={"nivel_senioridade": "senior", "area_atuacao_principal": "Dados"},
            )
        ]
        conteudo = _ranking_json({"candidato_id": 1, "posicao": 1, "justificativa": "Ótimo encaixe."})
        cliente = _OllamaClientFake(embedding=[1.0, 0.0], conteudo_chat=conteudo)

        resultados = await mod.buscar_candidatos(
            cliente, "modelo-teste", "modelo-embed", "descrição", candidatos
        )

        assert resultados[0].nivel_senioridade == "senior"
        assert resultados[0].area_atuacao_principal == "Dados"
        assert resultados[0].perfil_estruturado == {
            "nivel_senioridade": "senior",
            "area_atuacao_principal": "Dados",
        }

    async def test_candidato_sem_perfil_estruturado_usa_valores_padrao(self):
        candidatos = [_candidato(1, [1.0, 0.0], "Ana")]
        conteudo = _ranking_json({"candidato_id": 1, "posicao": 1, "justificativa": "..."})
        cliente = _OllamaClientFake(embedding=[1.0, 0.0], conteudo_chat=conteudo)

        resultados = await mod.buscar_candidatos(
            cliente, "modelo-teste", "modelo-embed", "descrição", candidatos
        )

        assert resultados[0].nivel_senioridade == "nao_identificado"
        assert resultados[0].area_atuacao_principal == "Não identificado"

    async def test_candidato_fora_do_shortlist_e_descartado(self):
        # 8 candidatos bem similares (id 1-8) + 1 bem diferente (id 9) — só
        # os 8 mais similares entram no shortlist mandado pra IA, então um
        # ranking que cita o id 9 (inventado, já que nem foi enviado) é
        # descartado.
        candidatos = [_candidato(i, [1.0, 0.0]) for i in range(1, 9)] + [_candidato(9, [0.0, 1.0])]
        conteudo = _ranking_json(
            {"candidato_id": 9, "posicao": 1, "justificativa": "..."},
            {"candidato_id": 1, "posicao": 2, "justificativa": "..."},
        )
        cliente = _OllamaClientFake(embedding=[1.0, 0.0], conteudo_chat=conteudo)

        resultados = await mod.buscar_candidatos(
            cliente, "modelo-teste", "modelo-embed", "descrição", candidatos
        )

        assert [resultado.candidato_id for resultado in resultados] == [1]

    async def test_sem_candidatos_levanta_indisponivel_sem_chamar_ollama(self):
        cliente = _OllamaClientFake(levantar_embed=AssertionError("não deveria ter chamado o Ollama"))
        with pytest.raises(AnaliseIndisponivel):
            await mod.buscar_candidatos(cliente, "modelo-teste", "modelo-embed", "descrição", [])

    async def test_falha_ao_gerar_embedding_levanta_indisponivel(self):
        candidatos = [_candidato(1, [1.0, 0.0])]
        cliente = _OllamaClientFake(levantar_embed=ConnectionError("Ollama fora do ar"))
        with pytest.raises(AnaliseIndisponivel):
            await mod.buscar_candidatos(cliente, "modelo-teste", "modelo-embed", "descrição", candidatos)

    async def test_falha_no_ranking_final_levanta_indisponivel(self):
        candidatos = [_candidato(1, [1.0, 0.0])]
        cliente = _OllamaClientFake(embedding=[1.0, 0.0], levantar_chat=ConnectionError("Ollama fora do ar"))
        with pytest.raises(AnaliseIndisponivel):
            await mod.buscar_candidatos(cliente, "modelo-teste", "modelo-embed", "descrição", candidatos)

    async def test_nenhum_resultado_valido_levanta_indisponivel(self):
        candidatos = [_candidato(1, [1.0, 0.0])]
        conteudo = _ranking_json({"candidato_id": 999, "posicao": 1, "justificativa": "..."})
        cliente = _OllamaClientFake(embedding=[1.0, 0.0], conteudo_chat=conteudo)
        with pytest.raises(AnaliseIndisponivel):
            await mod.buscar_candidatos(cliente, "modelo-teste", "modelo-embed", "descrição", candidatos)

    async def test_resposta_json_valida_mas_nao_objeto_levanta_indisponivel(self):
        candidatos = [_candidato(1, [1.0, 0.0])]
        cliente = _OllamaClientFake(embedding=[1.0, 0.0], conteudo_chat=json.dumps(None))
        with pytest.raises(AnaliseIndisponivel):
            await mod.buscar_candidatos(cliente, "modelo-teste", "modelo-embed", "descrição", candidatos)

    async def test_candidato_com_embedding_de_dimensao_diferente_nao_derruba_a_busca(self):
        # Candidato 1 tem embedding "antigo" (2 dimensões, modelo trocado
        # depois) — a busca não deve quebrar por causa dele, só tratar a
        # similaridade dele como 0 e seguir com os outros candidatos.
        candidatos = [_candidato(1, [1.0, 0.0, 0.0]), _candidato(2, [1.0, 0.0])]
        conteudo = _ranking_json({"candidato_id": 2, "posicao": 1, "justificativa": "..."})
        cliente = _OllamaClientFake(embedding=[1.0, 0.0], conteudo_chat=conteudo)

        resultados = await mod.buscar_candidatos(
            cliente, "modelo-teste", "modelo-embed", "descrição", candidatos
        )

        assert [resultado.candidato_id for resultado in resultados] == [2]
