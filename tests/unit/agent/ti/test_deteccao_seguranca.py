import json

from agente_oracle.agent.ti import deteccao_seguranca as mod
from agente_oracle.agent.ti.perfil_login import PerfilLogin, PerfilLoginProtheus
from agente_oracle.tools.ti.acessos_dados import PerfilAcesso


class _RespostaFake:
    def __init__(self, conteudo: str | None):
        self.message = type("Mensagem", (), {"content": conteudo})()


class _OllamaClientFake:
    """`detectar` só usa `chat(...)` — um fake simples já satisfaz essa
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


def _achado(usuario: str, **overrides) -> dict:
    base = {
        "usuario": usuario,
        "sistema": "agente_oracle",
        "tipo": "tentativa_invasao",
        "descricao": "...",
        "evidencia": "5 falhas",
    }
    base.update(overrides)
    return base


def _perfil_login(usuario: str, **overrides) -> PerfilLogin:
    base = {"login_falha": 0, "login_sucesso": 0, "conta_bloqueada": 0}
    base.update(overrides)
    return PerfilLogin(usuario=usuario, **base)


def _perfil_login_protheus(usuario: str, **overrides) -> PerfilLoginProtheus:
    base = {
        "total_logins": 1,
        "ips_distintos": 1,
        "maquinas_distintas": 1,
        "tentativas_bloqueio": 0,
        "bloqueado": False,
    }
    base.update(overrides)
    return PerfilLoginProtheus(usuario=usuario, **base)


def _perfil_acesso(usuario_id: str, **overrides) -> PerfilAcesso:
    base = {
        "modulo": "financeiro",
        "recurso": "posicao_titulos:listar",
        "total_registros": 10,
        "ocorrencias": 1,
    }
    base.update(overrides)
    return PerfilAcesso(usuario_id=usuario_id, **base)


class TestAchadoValido:
    def test_dict_com_todos_os_campos_e_valido(self):
        assert mod._achado_valido(_achado("joao")) is True

    def test_campo_faltando_e_invalido(self):
        achado = _achado("joao")
        del achado["descricao"]
        assert mod._achado_valido(achado) is False

    def test_campo_vazio_e_invalido(self):
        assert mod._achado_valido(_achado("joao", evidencia="")) is False

    def test_tipo_fora_do_conjunto_e_invalido(self):
        assert mod._achado_valido(_achado("joao", tipo="outro_tipo_qualquer")) is False

    def test_sistema_fora_do_conjunto_e_invalido(self):
        assert mod._achado_valido(_achado("joao", sistema="outro_sistema_qualquer")) is False

    def test_nao_dict_e_invalido(self):
        assert mod._achado_valido("nao é um dict") is False


class TestDetectar:
    async def test_sem_perfis_nao_chama_o_ollama(self):
        cliente = _OllamaClientFake(levantar=AssertionError("não deveria ter chamado o Ollama"))
        resultado = await mod.detectar(cliente, "modelo-teste", [], [], [])
        assert resultado == []

    async def test_achado_com_usuario_valido_e_devolvido(self):
        conteudo = _achados_json(
            _achado(
                "joao",
                descricao="Muitas falhas de login seguidas.",
                evidencia="6 falhas, 1 bloqueio",
            )
        )
        cliente = _OllamaClientFake(conteudo=conteudo)
        perfis_login = [_perfil_login("joao", login_falha=6, conta_bloqueada=1)]

        resultado = await mod.detectar(cliente, "modelo-teste", perfis_login, [], [])

        assert len(resultado) == 1
        assert resultado[0].usuario == "joao"
        assert resultado[0].sistema == "agente_oracle"
        assert resultado[0].tipo == "tentativa_invasao"

    async def test_achado_no_protheus_usa_perfil_de_login_protheus(self):
        conteudo = _achados_json(
            _achado(
                "maria",
                sistema="protheus",
                descricao="Login de vários IPs/máquinas diferentes.",
                evidencia="4 IPs distintos, 3 máquinas distintas",
            )
        )
        cliente = _OllamaClientFake(conteudo=conteudo)
        perfis_login_protheus = [_perfil_login_protheus("maria", ips_distintos=4, maquinas_distintas=3)]

        resultado = await mod.detectar(cliente, "modelo-teste", [], perfis_login_protheus, [])

        assert len(resultado) == 1
        assert resultado[0].usuario == "maria"
        assert resultado[0].sistema == "protheus"

    async def test_achado_de_acesso_a_dado_usa_perfil_de_acesso(self):
        conteudo = _achados_json(
            _achado(
                "maria",
                tipo="acesso_dados_suspeito",
                descricao="Volume de exportação muito acima do normal.",
                evidencia="5000 registros em 1 acesso",
            )
        )
        cliente = _OllamaClientFake(conteudo=conteudo)
        perfis_acesso = [_perfil_acesso("maria", total_registros=5000, ocorrencias=1)]

        resultado = await mod.detectar(cliente, "modelo-teste", [], [], perfis_acesso)

        assert len(resultado) == 1
        assert resultado[0].usuario == "maria"

    async def test_achado_com_usuario_inventado_e_descartado(self):
        conteudo = _achados_json(_achado("usuario-que-nao-existe"))
        cliente = _OllamaClientFake(conteudo=conteudo)
        perfis_login = [_perfil_login("joao", login_falha=1)]

        resultado = await mod.detectar(cliente, "modelo-teste", perfis_login, [], [])

        assert resultado == []

    async def test_json_invalido_devolve_lista_vazia(self):
        cliente = _OllamaClientFake(conteudo="isso não é json")
        resultado = await mod.detectar(cliente, "modelo-teste", [_perfil_login("joao")], [], [])
        assert resultado == []

    async def test_falha_do_ollama_devolve_lista_vazia(self):
        cliente = _OllamaClientFake(levantar=ConnectionError("Ollama fora do ar"))
        resultado = await mod.detectar(cliente, "modelo-teste", [_perfil_login("joao")], [], [])
        assert resultado == []

    async def test_chave_achados_ausente_devolve_lista_vazia(self):
        cliente = _OllamaClientFake(conteudo=json.dumps({}))
        resultado = await mod.detectar(cliente, "modelo-teste", [_perfil_login("joao")], [], [])
        assert resultado == []
