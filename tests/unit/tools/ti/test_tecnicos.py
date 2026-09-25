import pytest

from agente_oracle.tools.ti import tecnicos as mod
from agente_oracle.tools.ti.tecnicos import SemTecnicoNaArea, escolher_tecnico, tecnicos_da_area


def _linha(nome: str, tecnico_glpi_id: str, area_ti: str) -> dict:
    return {"usuario": tecnico_glpi_id, "nome": nome, "tecnico_glpi_id": tecnico_glpi_id, "area_ti": area_ti}


_ROSTER_TESTE = [
    _linha("Infra 1", "infra1", "infra"),
    _linha("Infra 2", "infra2", "infra"),
    _linha("Sistemas 1", "sistemas1", "sistemas"),
    _linha("Processos 1", "processos1", "processos"),
]


def _com_roster(monkeypatch, roster: list[dict] = _ROSTER_TESTE) -> None:
    """`todos_os_tecnicos`/`tecnicos_da_area`/`escolher_tecnico` leem de
    `tools.auth.usuarios.listar_tecnicos_ti` (Postgres) — troca por um
    roster controlado, sem precisar de banco real no teste unitário."""
    monkeypatch.setattr(mod, "listar_tecnicos_ti", lambda: roster)


class TestTecnicosDaArea:
    def test_devolve_so_a_area_pedida(self, monkeypatch):
        _com_roster(monkeypatch)
        assert all(tecnico.area == "infra" for tecnico in tecnicos_da_area("infra"))

    def test_area_existente_devolve_ao_menos_um(self, monkeypatch):
        _com_roster(monkeypatch)
        assert len(tecnicos_da_area("processos")) > 0
        assert len(tecnicos_da_area("sistemas")) > 0
        assert len(tecnicos_da_area("infra")) > 0

    def test_area_sem_ninguem_no_roster_devolve_vazio(self, monkeypatch):
        _com_roster(monkeypatch, [_linha("Infra 1", "infra1", "infra")])
        assert tecnicos_da_area("processos") == ()


class TestEscolherTecnico:
    """`escolher_tecnico` lê do roster vindo do banco (`todos_os_tecnicos`)
    — `monkeypatch` troca `listar_tecnicos_ti` por um roster controlado
    nesses testes, em vez de depender de Postgres real."""

    def test_escolhe_o_de_menor_carga(self, monkeypatch):
        _com_roster(monkeypatch)
        tecnico = escolher_tecnico("infra", {"infra1": 5, "infra2": 1})
        assert tecnico.identificador == "infra2"

    def test_tecnico_sem_carga_registrada_conta_como_zero(self, monkeypatch):
        _com_roster(monkeypatch)
        tecnico = escolher_tecnico("infra", {"infra1": 3})
        assert tecnico.identificador == "infra2"

    def test_empate_resolve_pela_ordem_do_roster(self, monkeypatch):
        _com_roster(monkeypatch)
        tecnico = escolher_tecnico("infra", {"infra1": 2, "infra2": 2})
        assert tecnico.identificador == "infra1"

    def test_cargas_vazias_escolhe_o_primeiro_do_roster(self, monkeypatch):
        _com_roster(monkeypatch)
        tecnico = escolher_tecnico("infra", {})
        assert tecnico.identificador == "infra1"

    def test_area_sem_ninguem_levanta_sem_tecnico_na_area(self, monkeypatch):
        # Antes disso, `min()` de uma lista vazia estourava `ValueError` cru
        # — virava 500 sem mensagem útil em `chamado_verificar_route`. Mais
        # raro agora que técnico é obrigatório pra papel de TI, mas ainda
        # possível (ex: único técnico de uma área foi apagado).
        _com_roster(monkeypatch, [_linha("Infra 1", "infra1", "infra")])

        with pytest.raises(SemTecnicoNaArea) as excinfo:
            escolher_tecnico("processos", {})

        assert excinfo.value.area == "processos"


_ROSTER_NOMES = [
    _linha("Pablo Silva", "pablo", "infra"),
    _linha("Denner Souza", "denner", "infra"),
    _linha("Suellen Lima", "suellen", "sistemas"),
]


class TestEscolherTecnicoComTextoChamado:
    """`texto_chamado` dá prioridade a um técnico citado pelo nome, mas só
    quando a citação é inequívoca — ver `_tecnico_citado_por_nome`."""

    def test_cita_um_unico_tecnico_da_area_ignora_a_carga(self, monkeypatch):
        _com_roster(monkeypatch, _ROSTER_NOMES)
        tecnico = escolher_tecnico("infra", {"pablo": 5, "denner": 0}, "Abrir chamado pro Pablo, por favor")
        assert tecnico.identificador == "pablo"

    def test_nome_citado_fora_da_area_e_ignorado(self, monkeypatch):
        _com_roster(monkeypatch, _ROSTER_NOMES)
        tecnico = escolher_tecnico("infra", {"pablo": 5, "denner": 0}, "Chamado pra Suellen")
        assert tecnico.identificador == "denner"

    def test_dois_nomes_citados_cai_na_carga(self, monkeypatch):
        _com_roster(monkeypatch, _ROSTER_NOMES)
        tecnico = escolher_tecnico("infra", {"pablo": 5, "denner": 0}, "Pablo e Denner, vejam isso")
        assert tecnico.identificador == "denner"

    def test_nome_dentro_de_outra_palavra_nao_conta(self, monkeypatch):
        _com_roster(monkeypatch, _ROSTER_NOMES)
        tecnico = escolher_tecnico("infra", {"pablo": 5, "denner": 0}, "Erro no PabloSistema")
        assert tecnico.identificador == "denner"

    def test_texto_vazio_usa_so_a_carga(self, monkeypatch):
        _com_roster(monkeypatch, _ROSTER_NOMES)
        tecnico = escolher_tecnico("infra", {"pablo": 5, "denner": 0}, "")
        assert tecnico.identificador == "denner"

    def test_acento_e_maiuscula_nao_importam(self, monkeypatch):
        roster = [_linha("José Ávila", "jose", "infra"), _linha("Denner Souza", "denner", "infra")]
        _com_roster(monkeypatch, roster)
        tecnico = escolher_tecnico("infra", {"jose": 5, "denner": 0}, "chamado pro JOSÉ, por favor")
        assert tecnico.identificador == "jose"
