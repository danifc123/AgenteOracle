import json

from agente_oracle.agent.auditoria import analise as mod
from agente_oracle.agent.auditoria.perfil_campo import PerfilCampo


class _RespostaFake:
    def __init__(self, conteudo: str | None):
        self.message = type("Mensagem", (), {"content": conteudo})()


class _OllamaClientFake:
    """`analisar_perfis` só usa `chat(...)` — um fake simples já satisfaz essa
    interface, sem precisar de um servidor Ollama de verdade."""

    def __init__(self, conteudo: str | None = None, levantar: Exception | None = None):
        self._conteudo = conteudo
        self._levantar = levantar

    async def chat(self, **_kwargs):
        if self._levantar:
            raise self._levantar
        return _RespostaFake(self._conteudo)


def _achados_json(*achados: dict) -> str:
    return json.dumps({"achados": list(achados)})


class TestAchadoValido:
    def test_dict_com_todos_os_campos_e_valido(self):
        achado = {
            "modulo": "financeiro",
            "view": "vw_clientes",
            "campo": "estado",
            "valor": "XX",
            "descricao": "...",
        }
        assert mod._achado_valido(achado) is True

    def test_campo_faltando_e_invalido(self):
        achado = {"modulo": "financeiro", "view": "vw_clientes", "campo": "estado", "valor": "XX"}
        assert mod._achado_valido(achado) is False

    def test_campo_vazio_e_invalido(self):
        achado = {
            "modulo": "financeiro",
            "view": "vw_clientes",
            "campo": "estado",
            "valor": "",
            "descricao": "...",
        }
        assert mod._achado_valido(achado) is False

    def test_nao_dict_e_invalido(self):
        assert mod._achado_valido("nao é um dict") is False


class TestAchadoFundamentado:
    _PERFIS = {
        ("financeiro", "vw_clientes", "filial"): ({"0101", "0102", "1908745"}, "0101"),
    }

    def test_valor_real_e_nao_e_o_mais_comum_e_fundamentado(self):
        achado = {"modulo": "financeiro", "view": "vw_clientes", "campo": "filial", "valor": "1908745"}
        assert mod._achado_fundamentado(achado, self._PERFIS) is True

    def test_valor_que_nao_esta_no_perfil_e_descartado(self):
        achado = {"modulo": "financeiro", "view": "vw_clientes", "campo": "filial", "valor": "9999999"}
        assert mod._achado_fundamentado(achado, self._PERFIS) is False

    def test_view_campo_errados_sao_descartados_mesmo_com_valor_real(self):
        # "1908745" é um valor real do perfil (filial), mas anexado a um
        # (view, campo) que não tem nada a ver — não pode passar só porque o
        # valor existe em ALGUM perfil.
        achado = {"modulo": "financeiro", "view": "vw_fornecedores", "campo": "cnpj_cpf", "valor": "1908745"}
        assert mod._achado_fundamentado(achado, self._PERFIS) is False

    def test_valor_mais_comum_e_descartado_quando_ha_mais_de_um_valor(self):
        achado = {"modulo": "financeiro", "view": "vw_clientes", "campo": "filial", "valor": "0101"}
        assert mod._achado_fundamentado(achado, self._PERFIS) is False

    def test_valor_unico_do_perfil_nao_e_descartado_por_ser_o_mais_comum(self):
        perfis = {("financeiro", "vw_clientes", "estado"): ({"MT"}, "MT")}
        achado = {"modulo": "financeiro", "view": "vw_clientes", "campo": "estado", "valor": "MT"}
        assert mod._achado_fundamentado(achado, perfis) is True


class TestFiltrarValoresConhecidos:
    def test_remove_so_o_valor_conhecido_mantendo_o_resto_do_perfil(self):
        perfil = PerfilCampo(
            modulo="financeiro", view="vw_clientes", campo="filial", valores=(("0101", 40), ("1908745", 1))
        )
        conhecidos = {("financeiro", "vw_clientes", "filial", "1908745")}
        resultado = mod.filtrar_valores_conhecidos([perfil], conhecidos)
        assert resultado == [
            PerfilCampo(modulo="financeiro", view="vw_clientes", campo="filial", valores=(("0101", 40),))
        ]

    def test_perfil_que_fica_sem_nenhum_valor_e_descartado_inteiro(self):
        perfil = PerfilCampo(
            modulo="financeiro", view="vw_clientes", campo="filial", valores=(("1908745", 1),)
        )
        conhecidos = {("financeiro", "vw_clientes", "filial", "1908745")}
        assert mod.filtrar_valores_conhecidos([perfil], conhecidos) == []

    def test_tupla_de_outro_modulo_view_ou_campo_nao_remove_por_engano(self):
        perfil = PerfilCampo(
            modulo="financeiro", view="vw_clientes", campo="filial", valores=(("1908745", 1),)
        )
        conhecidos = {("financeiro", "vw_fornecedores", "filial", "1908745")}
        assert mod.filtrar_valores_conhecidos([perfil], conhecidos) == [perfil]

    def test_sem_conhecidos_devolve_os_perfis_intactos(self):
        perfil = PerfilCampo(
            modulo="financeiro", view="vw_clientes", campo="filial", valores=(("1908745", 1),)
        )
        assert mod.filtrar_valores_conhecidos([perfil], set()) == [perfil]


class TestAnalisarPerfis:
    _PERFIL = PerfilCampo(
        modulo="financeiro", view="vw_clientes", campo="filial", valores=(("0101", 40), ("1908745", 1))
    )

    async def test_lista_vazia_de_perfis_nao_chama_o_ollama(self):
        cliente = _OllamaClientFake(levantar=AssertionError("não deveria ter chamado o Ollama"))
        resultado = await mod.analisar_perfis(cliente, "modelo-teste", [])
        assert resultado == []

    async def test_perfis_sem_nenhum_valor_sao_ignorados(self):
        perfil_vazio = PerfilCampo(modulo="financeiro", view="vw_clientes", campo="estado", valores=())
        cliente = _OllamaClientFake(levantar=AssertionError("não deveria ter chamado o Ollama"))
        resultado = await mod.analisar_perfis(cliente, "modelo-teste", [perfil_vazio])
        assert resultado == []

    async def test_achado_fundamentado_e_devolvido(self):
        conteudo = _achados_json(
            {
                "modulo": "financeiro",
                "view": "vw_clientes",
                "campo": "filial",
                "valor": "1908745",
                "descricao": "Analise a filial 1908745, ela parece estar fora do padrão.",
            }
        )
        cliente = _OllamaClientFake(conteudo=conteudo)
        resultado = await mod.analisar_perfis(cliente, "modelo-teste", [self._PERFIL])
        assert len(resultado) == 1
        assert resultado[0].valor == "1908745"

    async def test_achado_com_valor_inventado_e_descartado(self):
        conteudo = _achados_json(
            {
                "modulo": "financeiro",
                "view": "vw_clientes",
                "campo": "filial",
                "valor": "9999999",
                "descricao": "Valor que não veio do perfil.",
            }
        )
        cliente = _OllamaClientFake(conteudo=conteudo)
        resultado = await mod.analisar_perfis(cliente, "modelo-teste", [self._PERFIL])
        assert resultado == []

    async def test_json_invalido_devolve_lista_vazia(self):
        cliente = _OllamaClientFake(conteudo="isso não é json")
        resultado = await mod.analisar_perfis(cliente, "modelo-teste", [self._PERFIL])
        assert resultado == []

    async def test_falha_do_ollama_devolve_lista_vazia(self):
        cliente = _OllamaClientFake(levantar=ConnectionError("Ollama fora do ar"))
        resultado = await mod.analisar_perfis(cliente, "modelo-teste", [self._PERFIL])
        assert resultado == []

    async def test_chave_achados_ausente_devolve_lista_vazia(self):
        cliente = _OllamaClientFake(conteudo=json.dumps({}))
        resultado = await mod.analisar_perfis(cliente, "modelo-teste", [self._PERFIL])
        assert resultado == []
