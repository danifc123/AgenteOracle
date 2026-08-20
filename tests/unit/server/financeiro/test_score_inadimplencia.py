from agente_oracle.agent.financeiro.clima_regional import IndicadorClima
from agente_oracle.agent.financeiro.score_inadimplencia import (
    ComportamentoPagamentoCliente,
    ScoreInadimplencia,
)
from agente_oracle.server.financeiro.score_inadimplencia import (
    _apenas_com_risco,
    _coordenada_valida,
    _resolver_clima,
    _rotulo_localizacao,
    _score_para_json,
)
from agente_oracle.tools.financeiro.localizacao_cliente import LocalizacaoCliente


def _score(cliente_codigo: str, valor: int) -> ScoreInadimplencia:
    return ScoreInadimplencia(
        cliente_codigo=cliente_codigo,
        cliente_nome=f"Cliente {cliente_codigo}",
        score=valor,
        comportamento=ComportamentoPagamentoCliente(
            cliente_codigo=cliente_codigo,
            cliente_nome=f"Cliente {cliente_codigo}",
            percentual_atraso_recente=0.0,
            percentual_atraso_anterior=0.0,
            dias_atraso_medio=0.0,
            tendencia="estavel",
        ),
        clima=None,
        safra_ativa=None,
        fatores=(),
    )


class TestApenasComRisco:
    def test_score_zero_fica_de_fora(self):
        scores = [_score("C1", 0), _score("C2", 10)]
        assert [s.cliente_codigo for s in _apenas_com_risco(scores)] == ["C2"]

    def test_qualquer_score_positivo_aparece(self):
        scores = [_score("C1", 1), _score("C2", 100)]
        assert len(_apenas_com_risco(scores)) == 2

    def test_lista_vazia_continua_vazia(self):
        assert _apenas_com_risco([]) == []

    def test_todos_com_score_zero_devolve_vazio(self):
        scores = [_score("C1", 0), _score("C2", 0)]
        assert _apenas_com_risco(scores) == []


class TestResolverClima:
    def test_localizacao_cadastrada_resolvida_tem_prioridade(self):
        clima_cadastrado = IndicadorClima("Fazenda Santa Luzia", "cadastro", -80.0, "seca")
        clima_municipio = IndicadorClima("Sorriso", "MT", 5.0, "normal")
        clima = _resolver_clima(
            "C1",
            municipios_por_cliente={"C1": ("Sorriso", "MT")},
            climas_por_municipio={("Sorriso", "MT"): clima_municipio},
            climas_por_cliente_cadastrado={"C1": clima_cadastrado},
        )
        assert clima is clima_cadastrado

    def test_sem_cadastro_cai_no_municipio(self):
        clima_municipio = IndicadorClima("Sorriso", "MT", 5.0, "normal")
        clima = _resolver_clima(
            "C1",
            municipios_por_cliente={"C1": ("Sorriso", "MT")},
            climas_por_municipio={("Sorriso", "MT"): clima_municipio},
            climas_por_cliente_cadastrado={},
        )
        assert clima is clima_municipio

    def test_cadastro_nao_resolvido_cai_no_municipio(self):
        # cliente cadastrou mas não resolveu (texto não geocodificado) -> não
        # entra em climas_por_cliente_cadastrado, cai no fallback normal.
        clima_municipio = IndicadorClima("Sorriso", "MT", 5.0, "normal")
        clima = _resolver_clima(
            "C1",
            municipios_por_cliente={"C1": ("Sorriso", "MT")},
            climas_por_municipio={("Sorriso", "MT"): clima_municipio},
            climas_por_cliente_cadastrado={},
        )
        assert clima is clima_municipio

    def test_sem_cadastro_e_sem_municipio_devolve_none(self):
        clima = _resolver_clima(
            "C1", municipios_por_cliente={}, climas_por_municipio={}, climas_por_cliente_cadastrado={}
        )
        assert clima is None


class TestScoreParaJson:
    # Achado do usuário testando: cadastro que não resolveu (texto de endereço
    # que a geocodificação não reconheceu) precisa continuar mostrando esse
    # estado depois de recalcular a tela, não só logo após salvar — senão
    # parece que o cadastro "funcionou" quando na verdade o clima caiu pro
    # fallback de município.
    def test_localizacao_nao_resolvida_aparece_como_nao_resolvida_no_json(self):
        localizacao = LocalizacaoCliente(
            cliente_codigo="C1",
            cidade="Rio de Janeiro",
            bairro="Jardim Excelsior",
            latitude=None,
            longitude=None,
            resolvido=False,
        )
        json_saida = _score_para_json(_score("C1", 10), localizacao)
        assert json_saida["localizacao"]["cidade"] == "Rio de Janeiro"
        assert json_saida["localizacao"]["bairro"] == "Jardim Excelsior"
        assert json_saida["localizacao"]["resolvido"] is False

    def test_localizacao_resolvida_aparece_como_resolvida_no_json(self):
        localizacao = LocalizacaoCliente(
            cliente_codigo="C1",
            cidade="Sorriso",
            bairro=None,
            latitude=-12.5,
            longitude=-55.7,
            resolvido=True,
        )
        json_saida = _score_para_json(_score("C1", 10), localizacao)
        assert json_saida["localizacao"]["resolvido"] is True

    def test_sem_cadastro_devolve_null(self):
        json_saida = _score_para_json(_score("C1", 10), None)
        assert json_saida["localizacao"] is None


class TestRotuloLocalizacao:
    def test_cidade_e_bairro(self):
        localizacao = LocalizacaoCliente(
            cliente_codigo="C1",
            cidade="Cabo Frio",
            bairro="Jardim Excelsior",
            latitude=-22.8,
            longitude=-42.0,
            resolvido=True,
        )
        assert _rotulo_localizacao(localizacao) == "Jardim Excelsior, Cabo Frio"

    def test_so_cidade(self):
        localizacao = LocalizacaoCliente(
            cliente_codigo="C1",
            cidade="Cabo Frio",
            bairro=None,
            latitude=-22.8,
            longitude=-42.0,
            resolvido=True,
        )
        assert _rotulo_localizacao(localizacao) == "Cabo Frio"

    def test_so_coordenada_sem_cidade(self):
        localizacao = LocalizacaoCliente(
            cliente_codigo="C1", cidade=None, bairro=None, latitude=-22.8, longitude=-42.0, resolvido=True
        )
        assert _rotulo_localizacao(localizacao) == "-22.8, -42.0"


class TestCoordenadaValida:
    def test_dentro_da_faixa_e_valida(self):
        assert _coordenada_valida(-17.9, -51.1) is True

    def test_latitude_fora_da_faixa_e_invalida(self):
        assert _coordenada_valida(-95.0, -51.0) is False

    def test_longitude_fora_da_faixa_e_invalida(self):
        assert _coordenada_valida(-17.0, -185.0) is False

    def test_latitude_none_e_invalida(self):
        assert _coordenada_valida(None, -51.0) is False

    def test_longitude_none_e_invalida(self):
        assert _coordenada_valida(-17.0, None) is False
