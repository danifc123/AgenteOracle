import json

from agente_oracle.agent.ti import qualidade_chamado as mod

_DESCRICAO_LONGA = (
    "O sistema financeiro trava sempre que tento gerar o relatório de vendas do mês passado desde ontem"
)
_DESCRICAO_CURTA = "não tá funcionando"


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


def _chat_nunca_chamado(**_kwargs):
    raise AssertionError("chat() não deveria ser chamado com usar_ia=False")


def _avaliacao_json(suficiente: bool, mensagem: str = "") -> str:
    return json.dumps({"suficiente": suficiente, "mensagem": mensagem})


class TestAvaliarPorRegra:
    def test_descricao_com_15_palavras_ou_mais_e_suficiente(self):
        avaliacao = mod._avaliar_por_regra(_DESCRICAO_LONGA)
        assert avaliacao.suficiente is True
        assert avaliacao.mensagem == ""

    def test_descricao_com_menos_de_15_palavras_e_insuficiente(self):
        avaliacao = mod._avaliar_por_regra(_DESCRICAO_CURTA)
        assert avaliacao.suficiente is False
        assert avaliacao.mensagem != ""


class TestAvaliarChamado:
    async def test_chamado_suficiente_nao_traz_mensagem(self):
        cliente = _OllamaClientFake(conteudo=_avaliacao_json(True))

        avaliacao = await mod.avaliar_chamado(
            cliente, "modelo-teste", "Título", "Descrição detalhada", "Sistemas"
        )

        assert avaliacao.suficiente is True

    async def test_chamado_insuficiente_traz_a_pergunta_da_ia(self):
        cliente = _OllamaClientFake(conteudo=_avaliacao_json(False, "Qual sistema está afetado?"))

        avaliacao = await mod.avaliar_chamado(cliente, "modelo-teste", "Não funciona", _DESCRICAO_CURTA, "TI")

        assert avaliacao.suficiente is False
        assert avaliacao.mensagem == "Qual sistema está afetado?"

    async def test_insuficiente_sem_mensagem_cai_pra_regra(self):
        # IA respondeu, mas sem uma pergunta de verdade — não dá pra confiar
        # nesse julgamento, então quem decide é a regra de palavras.
        cliente = _OllamaClientFake(conteudo=_avaliacao_json(False, ""))

        avaliacao = await mod.avaliar_chamado(cliente, "modelo-teste", "Título", _DESCRICAO_LONGA, "Sistemas")

        assert avaliacao.suficiente is True

    async def test_falha_no_ollama_cai_pra_regra(self):
        cliente = _OllamaClientFake(levantar=ConnectionError("Ollama fora do ar"))

        avaliacao = await mod.avaliar_chamado(cliente, "modelo-teste", "Título", _DESCRICAO_LONGA, "Sistemas")

        assert avaliacao.suficiente is True

    async def test_falha_no_ollama_com_descricao_curta_cai_pra_regra_e_marca_insuficiente(self):
        cliente = _OllamaClientFake(levantar=ConnectionError("Ollama fora do ar"))

        avaliacao = await mod.avaliar_chamado(cliente, "modelo-teste", "Título", _DESCRICAO_CURTA, "Sistemas")

        assert avaliacao.suficiente is False
        assert avaliacao.mensagem != ""

    async def test_resposta_mal_formada_cai_pra_regra(self):
        cliente = _OllamaClientFake(conteudo="isso não é json")

        avaliacao = await mod.avaliar_chamado(cliente, "modelo-teste", "Título", _DESCRICAO_LONGA, "Sistemas")

        assert avaliacao.suficiente is True

    async def test_campo_suficiente_com_tipo_errado_cai_pra_regra(self):
        cliente = _OllamaClientFake(conteudo=json.dumps({"suficiente": "sim", "mensagem": "..."}))

        avaliacao = await mod.avaliar_chamado(cliente, "modelo-teste", "Título", _DESCRICAO_LONGA, "Sistemas")

        assert avaliacao.suficiente is True

    async def test_usar_ia_false_nunca_chama_o_ollama(self):
        cliente = _OllamaClientFake()
        cliente.chat = _chat_nunca_chamado

        avaliacao = await mod.avaliar_chamado(
            cliente, "modelo-teste", "Título", _DESCRICAO_LONGA, "Sistemas", usar_ia=False
        )

        assert avaliacao.suficiente is True

    async def test_usar_ia_false_com_descricao_curta_marca_insuficiente(self):
        cliente = _OllamaClientFake()
        cliente.chat = _chat_nunca_chamado

        avaliacao = await mod.avaliar_chamado(
            cliente, "modelo-teste", "Título", _DESCRICAO_CURTA, "Sistemas", usar_ia=False
        )

        assert avaliacao.suficiente is False
        assert avaliacao.mensagem != ""
