from agente_oracle.tools.ti import tecnicos as mod
from agente_oracle.tools.ti.tecnicos import Tecnico, escolher_tecnico, tecnicos_da_area

_INFRA_1 = Tecnico("Infra 1", "infra1", "infra")
_INFRA_2 = Tecnico("Infra 2", "infra2", "infra")


class TestTecnicosDaArea:
    def test_devolve_so_a_area_pedida(self):
        assert all(tecnico.area == "infra" for tecnico in tecnicos_da_area("infra"))

    def test_area_existente_devolve_ao_menos_um(self):
        assert len(tecnicos_da_area("processos")) > 0
        assert len(tecnicos_da_area("sistemas")) > 0
        assert len(tecnicos_da_area("infra")) > 0


class TestEscolherTecnico:
    """`escolher_tecnico` lê de `tools.ti.tecnicos.TECNICOS` (roster fixo do
    módulo) — `monkeypatch` troca por um roster controlado nesses testes,
    em vez de depender dos placeholders reais."""

    def test_escolhe_o_de_menor_carga(self, monkeypatch):
        monkeypatch.setattr(mod, "TECNICOS", (_INFRA_1, _INFRA_2))
        tecnico = escolher_tecnico("infra", {"infra1": 5, "infra2": 1})
        assert tecnico.identificador == "infra2"

    def test_tecnico_sem_carga_registrada_conta_como_zero(self, monkeypatch):
        monkeypatch.setattr(mod, "TECNICOS", (_INFRA_1, _INFRA_2))
        tecnico = escolher_tecnico("infra", {"infra1": 3})
        assert tecnico.identificador == "infra2"

    def test_empate_resolve_pela_ordem_fixa_do_roster(self, monkeypatch):
        monkeypatch.setattr(mod, "TECNICOS", (_INFRA_1, _INFRA_2))
        tecnico = escolher_tecnico("infra", {"infra1": 2, "infra2": 2})
        assert tecnico.identificador == "infra1"

    def test_cargas_vazias_escolhe_o_primeiro_do_roster(self, monkeypatch):
        monkeypatch.setattr(mod, "TECNICOS", (_INFRA_1, _INFRA_2))
        tecnico = escolher_tecnico("infra", {})
        assert tecnico.identificador == "infra1"
