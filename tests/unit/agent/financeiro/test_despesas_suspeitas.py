import json
from datetime import date, timedelta

from agente_oracle.agent.financeiro import despesas_suspeitas as mod


class _RespostaFake:
    def __init__(self, conteudo: str | None):
        self.message = type("Mensagem", (), {"content": conteudo})()


class _OllamaClientFake:
    def __init__(self, conteudo: str | None = None, levantar: Exception | None = None):
        self._conteudo = conteudo
        self._levantar = levantar

    async def chat(self, **_kwargs):
        if self._levantar:
            raise self._levantar
        return _RespostaFake(self._conteudo)


def _titulo(
    fornecedor_codigo: str = "F1",
    valor_original: float = 1000.0,
    dias_atras: int = 0,
    prefixo: str = "A",
    numero: str = "1",
    parcela: str = "01",
    natureza_codigo: str = "N1",
    fornecedor_nome: str = "Fornecedor Um",
    natureza_descricao: str = "Aluguel",
) -> mod.TituloPagar:
    return mod.TituloPagar(
        fornecedor_codigo=fornecedor_codigo,
        fornecedor_nome=fornecedor_nome,
        prefixo=prefixo,
        numero=numero,
        parcela=parcela,
        natureza_codigo=natureza_codigo,
        natureza_descricao=natureza_descricao,
        valor_original=valor_original,
        data_emissao=date.today() - timedelta(days=dias_atras),
    )


def _achados_json(*achados: dict) -> str:
    return json.dumps({"achados": list(achados)})


class TestCandidatosDuplicidade:
    def test_mesmo_fornecedor_valor_e_data_proxima_vira_candidato(self):
        titulos = [
            _titulo(numero="1", dias_atras=0),
            _titulo(numero="2", dias_atras=3),
        ]
        candidatos = mod._candidatos_duplicidade(titulos)
        assert len(candidatos) == 1
        assert set(candidatos[0].documentos) == {"A-1-01", "A-2-01"}

    def test_datas_distantes_nao_vira_candidato(self):
        titulos = [
            _titulo(numero="1", dias_atras=0),
            _titulo(numero="2", dias_atras=30),
        ]
        assert mod._candidatos_duplicidade(titulos) == []

    def test_titulo_unico_nao_vira_candidato(self):
        assert mod._candidatos_duplicidade([_titulo()]) == []

    def test_mesmas_parcelas_do_mesmo_documento_nao_conta_como_duplicidade(self):
        titulos = [
            _titulo(numero="1", parcela="01", dias_atras=0),
            _titulo(numero="1", parcela="02", dias_atras=0),
        ]
        assert mod._candidatos_duplicidade(titulos) == []

    def test_valores_diferentes_nao_agrupam(self):
        titulos = [
            _titulo(numero="1", valor_original=1000.0),
            _titulo(numero="2", valor_original=999.0),
        ]
        assert mod._candidatos_duplicidade(titulos) == []


class TestCandidatosAnomaliaValor:
    def _grupo_normal(self, natureza_codigo: str = "N1", quantidade: int = 5) -> list[mod.TituloPagar]:
        # Variação pequena e realista em torno de 1000 (nunca todos
        # idênticos) — desvio-padrão zero faria qualquer limiar colapsar
        # na própria média, o que não é o cenário que este teste quer cobrir.
        return [
            _titulo(
                numero=str(i),
                valor_original=1000.0 + (i - quantidade // 2) * 10,
                natureza_codigo=natureza_codigo,
            )
            for i in range(quantidade)
        ]

    def test_valor_muito_acima_da_media_vira_candidato(self):
        titulos = self._grupo_normal() + [_titulo(numero="alto", valor_original=100_000.0)]
        candidatos = mod._candidatos_anomalia_valor(titulos)
        assert len(candidatos) == 1
        assert candidatos[0].documento == "A-alto-01"

    def test_grupo_pequeno_demais_nao_gera_candidato_mesmo_com_valor_alto(self):
        titulos = self._grupo_normal(quantidade=3) + [_titulo(numero="alto", valor_original=100_000.0)]
        assert mod._candidatos_anomalia_valor(titulos) == []

    def test_valores_todos_iguais_nao_gera_candidato(self):
        titulos = [_titulo(numero=str(i), valor_original=1000.0) for i in range(5)]
        assert mod._candidatos_anomalia_valor(titulos) == []


class TestAnalisarDespesas:
    async def test_sem_candidato_nao_chama_ollama(self):
        cliente = _OllamaClientFake(levantar=AssertionError("não deveria ter chamado o Ollama"))
        achados = await mod.analisar_despesas(cliente, "modelo-teste", [])
        assert achados == []

    async def test_ia_confirma_candidato_de_duplicidade(self):
        titulos = [_titulo(numero="1", dias_atras=0), _titulo(numero="2", dias_atras=2)]
        conteudo = _achados_json(
            {
                "fornecedor_codigo": "F1",
                "valor_original": 1000.0,
                "tipo": "duplicidade",
                "descricao": "Mesmo valor e fornecedor em documentos diferentes, poucos dias de diferença.",
            }
        )
        cliente = _OllamaClientFake(conteudo=conteudo)

        achados = await mod.analisar_despesas(cliente, "modelo-teste", titulos)

        assert len(achados) == 1
        assert achados[0].tipo == "duplicidade"
        assert achados[0].fornecedor_nome == "Fornecedor Um"

    async def test_ia_descarta_candidato_nao_citado(self):
        titulos = [_titulo(numero="1", dias_atras=0), _titulo(numero="2", dias_atras=2)]
        cliente = _OllamaClientFake(conteudo=_achados_json())

        achados = await mod.analisar_despesas(cliente, "modelo-teste", titulos)

        assert achados == []

    async def test_achado_que_nao_bate_com_candidato_real_e_descartado(self):
        titulos = [_titulo(numero="1", dias_atras=0), _titulo(numero="2", dias_atras=2)]
        conteudo = _achados_json(
            {
                "fornecedor_codigo": "F1",
                "valor_original": 999999.0,  # não é o valor real do candidato
                "tipo": "duplicidade",
                "descricao": "...",
            }
        )
        cliente = _OllamaClientFake(conteudo=conteudo)

        achados = await mod.analisar_despesas(cliente, "modelo-teste", titulos)

        assert achados == []

    async def test_falha_no_ollama_devolve_candidatos_com_descricao_generica(self):
        titulos = [_titulo(numero="1", dias_atras=0), _titulo(numero="2", dias_atras=2)]
        cliente = _OllamaClientFake(levantar=ConnectionError("Ollama fora do ar"))

        achados = await mod.analisar_despesas(cliente, "modelo-teste", titulos)

        assert len(achados) == 1
        assert achados[0].tipo == "duplicidade"
        assert achados[0].descricao

    async def test_resposta_mal_formada_devolve_candidatos_com_descricao_generica(self):
        titulos = [_titulo(numero="1", dias_atras=0), _titulo(numero="2", dias_atras=2)]
        cliente = _OllamaClientFake(conteudo="isso não é json")

        achados = await mod.analisar_despesas(cliente, "modelo-teste", titulos)

        assert len(achados) == 1
        assert achados[0].tipo == "duplicidade"
