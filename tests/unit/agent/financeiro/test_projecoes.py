import json

from agente_oracle.agent.financeiro import projecoes as mod


class _RespostaFake:
    def __init__(self, conteudo: str | None):
        self.message = type("Mensagem", (), {"content": conteudo})()


class _OllamaClientFake:
    """`gerar_analise` só usa `chat(...)` — um fake simples já satisfaz essa
    interface, sem precisar de um servidor Ollama de verdade."""

    def __init__(self, conteudo: str | None = None, levantar: Exception | None = None):
        self._conteudo = conteudo
        self._levantar = levantar

    async def chat(self, **_kwargs):
        if self._levantar:
            raise self._levantar
        return _RespostaFake(self._conteudo)


class TestProjetarTendenciaLinear:
    def test_serie_perfeitamente_linear(self):
        resultado = mod.projetar_tendencia_linear([10.0, 20.0, 30.0, 40.0], 2)
        assert resultado == [50.0, 60.0]

    def test_serie_constante(self):
        resultado = mod.projetar_tendencia_linear([50.0, 50.0, 50.0], 2)
        assert resultado == [50.0, 50.0]

    def test_menos_de_dois_pontos_devolve_vazio(self):
        assert mod.projetar_tendencia_linear([], 3) == []
        assert mod.projetar_tendencia_linear([100.0], 3) == []

    def test_zero_meses_futuros_devolve_vazio(self):
        assert mod.projetar_tendencia_linear([10.0, 20.0], 0) == []


class TestProximosMeses:
    def test_mesmo_ano(self):
        assert mod.proximos_meses("2026-01", 2) == ["2026-02", "2026-03"]

    def test_virada_de_ano(self):
        assert mod.proximos_meses("2026-11", 3) == ["2026-12", "2027-01", "2027-02"]

    def test_quantidade_zero_devolve_vazio(self):
        assert mod.proximos_meses("2026-05", 0) == []


class TestGerarAnalise:
    async def test_devolve_analise_do_modelo(self):
        cliente = _OllamaClientFake(conteudo=json.dumps({"analise": "Tendência de alta nas vendas."}))
        resultado = await mod.gerar_analise(cliente, "modelo-teste", "contexto qualquer")
        assert resultado == "Tendência de alta nas vendas."

    async def test_resposta_vazia_cai_no_fallback(self):
        cliente = _OllamaClientFake(conteudo=json.dumps({"analise": ""}))
        resultado = await mod.gerar_analise(cliente, "modelo-teste", "contexto qualquer")
        assert resultado == mod._ANALISE_INDISPONIVEL

    async def test_json_invalido_cai_no_fallback(self):
        cliente = _OllamaClientFake(conteudo="isso não é json")
        resultado = await mod.gerar_analise(cliente, "modelo-teste", "contexto qualquer")
        assert resultado == mod._ANALISE_INDISPONIVEL

    async def test_falha_do_ollama_cai_no_fallback(self):
        cliente = _OllamaClientFake(levantar=ConnectionError("Ollama fora do ar"))
        resultado = await mod.gerar_analise(cliente, "modelo-teste", "contexto qualquer")
        assert resultado == mod._ANALISE_INDISPONIVEL
