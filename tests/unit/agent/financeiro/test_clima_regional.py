from agente_oracle.agent.financeiro.clima_regional import (
    buscar_indicador_clima,
    buscar_indicador_clima_por_coordenadas,
)


class _RespostaFake:
    def __init__(self, dados: dict):
        self._dados = dados

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._dados


class _HttpClienteFake:
    """`respostas_precipitacao` é consumida em ordem de chamada: a
    primeira serve a janela recente, as seguintes servem cada ano
    histórico (1..5). Um item pode ser uma `Exception` pra simular falha
    de rede naquela chamada específica."""

    def __init__(self, resposta_geocodificacao, respostas_precipitacao):
        self._resposta_geocodificacao = resposta_geocodificacao
        self._respostas_precipitacao = iter(respostas_precipitacao)

    async def get(self, url: str, params=None):
        resposta = self._resposta_geocodificacao if "geocoding" in url else next(self._respostas_precipitacao)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


def _geocodificacao(latitude: float = -15.6, longitude: float = -56.1) -> _RespostaFake:
    return _RespostaFake({"results": [{"latitude": latitude, "longitude": longitude}]})


def _geocodificacao_vazia() -> _RespostaFake:
    return _RespostaFake({"results": []})


def _precipitacao(total_por_dia: float, dias: int = 30) -> _RespostaFake:
    return _RespostaFake({"daily": {"precipitation_sum": [total_por_dia] * dias}})


class TestBuscarIndicadorClima:
    async def test_geocodificacao_sem_resultado_devolve_indisponivel(self):
        http_client = _HttpClienteFake(_geocodificacao_vazia(), [])
        indicador = await buscar_indicador_clima(http_client, "Cidade Inexistente", "XX")
        assert indicador.classificacao == "indisponivel"
        assert indicador.anomalia_precipitacao_percentual is None

    async def test_geocodificacao_com_falha_de_rede_devolve_indisponivel(self):
        http_client = _HttpClienteFake(ConnectionError("fora do ar"), [])
        indicador = await buscar_indicador_clima(http_client, "Cuiaba", "MT")
        assert indicador.classificacao == "indisponivel"

    async def test_precipitacao_recente_indisponivel_devolve_indisponivel(self):
        http_client = _HttpClienteFake(_geocodificacao(), [ConnectionError("fora do ar")])
        indicador = await buscar_indicador_clima(http_client, "Cuiaba", "MT")
        assert indicador.classificacao == "indisponivel"

    async def test_sem_nenhum_ano_historico_disponivel_devolve_indisponivel(self):
        respostas = [_precipitacao(2.0), *([ConnectionError("fora do ar")] * 5)]
        http_client = _HttpClienteFake(_geocodificacao(), respostas)
        indicador = await buscar_indicador_clima(http_client, "Cuiaba", "MT")
        assert indicador.classificacao == "indisponivel"

    async def test_seca_quando_precipitacao_recente_muito_abaixo_da_media(self):
        respostas = [_precipitacao(1.0), *([_precipitacao(20.0)] * 5)]
        http_client = _HttpClienteFake(_geocodificacao(), respostas)
        indicador = await buscar_indicador_clima(http_client, "Cuiaba", "MT")
        assert indicador.classificacao == "seca"
        assert indicador.anomalia_precipitacao_percentual < -50

    async def test_excesso_chuva_quando_precipitacao_recente_muito_acima_da_media(self):
        respostas = [_precipitacao(50.0), *([_precipitacao(10.0)] * 5)]
        http_client = _HttpClienteFake(_geocodificacao(), respostas)
        indicador = await buscar_indicador_clima(http_client, "Cuiaba", "MT")
        assert indicador.classificacao == "excesso_chuva"
        assert indicador.anomalia_precipitacao_percentual >= 100

    async def test_normal_quando_dentro_da_faixa_esperada(self):
        respostas = [_precipitacao(11.0), *([_precipitacao(10.0)] * 5)]
        http_client = _HttpClienteFake(_geocodificacao(), respostas)
        indicador = await buscar_indicador_clima(http_client, "Cuiaba", "MT")
        assert indicador.classificacao == "normal"


class TestBuscarIndicadorClimaPorCoordenadas:
    async def test_nao_chama_geocodificacao(self):
        respostas = [_precipitacao(11.0), *([_precipitacao(10.0)] * 5)]
        http_client = _HttpClienteFake(ConnectionError("geocoding não deveria ser chamado"), respostas)
        indicador = await buscar_indicador_clima_por_coordenadas(
            http_client, -15.6, -56.1, "Fazenda Santa Luzia", "MT"
        )
        assert indicador.classificacao == "normal"
        assert indicador.municipio_nome == "Fazenda Santa Luzia"

    async def test_precipitacao_indisponivel_devolve_indisponivel(self):
        http_client = _HttpClienteFake(None, [ConnectionError("fora do ar")])
        indicador = await buscar_indicador_clima_por_coordenadas(http_client, -15.6, -56.1, "Fazenda X", "MT")
        assert indicador.classificacao == "indisponivel"
