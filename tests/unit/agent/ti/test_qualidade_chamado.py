import json

from agente_oracle.agent.ti import qualidade_chamado as mod


class _RespostaFake:
    def __init__(self, conteudo: str | None):
        self.message = type("Mensagem", (), {"content": conteudo})()


class _OllamaClientFake:
    """`avaliar_chamado` só usa `chat(...)` — um fake simples já satisfaz
    essa interface, sem precisar de um servidor Ollama de verdade."""

    def __init__(self, conteudo: str | None = None, levantar: Exception | None = None):
        self._conteudo = conteudo
        self._levantar = levantar

    async def chat(self, **_kwargs):
        if self._levantar:
            raise self._levantar
        return _RespostaFake(self._conteudo)


def _avaliacao_json(suficiente: bool, mensagem: str = "") -> str:
    return json.dumps({"suficiente": suficiente, "mensagem": mensagem})


class TestAvaliarChamado:
    async def test_chamado_suficiente_nao_traz_mensagem(self):
        cliente = _OllamaClientFake(conteudo=_avaliacao_json(True))

        avaliacao = await mod.avaliar_chamado(
            cliente, "modelo-teste", "Título", "Descrição detalhada", "Sistemas"
        )

        assert avaliacao.suficiente is True

    async def test_chamado_insuficiente_traz_a_pergunta_da_ia(self):
        cliente = _OllamaClientFake(conteudo=_avaliacao_json(False, "Qual sistema está afetado?"))

        avaliacao = await mod.avaliar_chamado(
            cliente, "modelo-teste", "Não funciona", "não tá funcionando", "TI"
        )

        assert avaliacao.suficiente is False
        assert avaliacao.mensagem == "Qual sistema está afetado?"

    async def test_insuficiente_sem_mensagem_vira_suficiente(self):
        # Sem uma pergunta de verdade pro usuário, não vale reter o chamado.
        cliente = _OllamaClientFake(conteudo=_avaliacao_json(False, ""))

        avaliacao = await mod.avaliar_chamado(cliente, "modelo-teste", "Título", "Descrição", "Sistemas")

        assert avaliacao.suficiente is True

    async def test_falha_no_ollama_devolve_suficiente(self):
        cliente = _OllamaClientFake(levantar=ConnectionError("Ollama fora do ar"))

        avaliacao = await mod.avaliar_chamado(cliente, "modelo-teste", "Título", "Descrição", "Sistemas")

        assert avaliacao.suficiente is True
        assert avaliacao.mensagem == ""

    async def test_resposta_mal_formada_devolve_suficiente(self):
        cliente = _OllamaClientFake(conteudo="isso não é json")

        avaliacao = await mod.avaliar_chamado(cliente, "modelo-teste", "Título", "Descrição", "Sistemas")

        assert avaliacao.suficiente is True

    async def test_campo_suficiente_com_tipo_errado_devolve_suficiente(self):
        cliente = _OllamaClientFake(conteudo=json.dumps({"suficiente": "sim", "mensagem": "..."}))

        avaliacao = await mod.avaliar_chamado(cliente, "modelo-teste", "Título", "Descrição", "Sistemas")

        assert avaliacao.suficiente is True
