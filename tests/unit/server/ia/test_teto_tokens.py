import json

from agente_oracle.server.ia import teto_tokens as mod


class TestTetoValido:
    def test_inteiro_maior_ou_igual_a_zero_e_aceito(self):
        assert mod._teto_valido(0) is True
        assert mod._teto_valido(50000) is True

    def test_negativo_e_rejeitado(self):
        assert mod._teto_valido(-1) is False

    def test_bool_e_rejeitado(self):
        # `True` é `int` em Python — sem a checagem explícita viraria 1.
        assert mod._teto_valido(True) is False
        assert mod._teto_valido(False) is False

    def test_nao_inteiro_e_rejeitado(self):
        assert mod._teto_valido("50000") is False
        assert mod._teto_valido(12.5) is False
        assert mod._teto_valido(None) is False


class TestConsultar:
    def test_devolve_teto_e_consumo_de_hoje(self, monkeypatch):
        monkeypatch.setattr(mod.configuracoes_provedor, "teto_tokens_diario", lambda dominio: 1000)
        monkeypatch.setattr(mod.auditoria_externa, "tokens_hoje", lambda dominio: 250)

        resposta = mod._consultar("ti")

        corpo = json.loads(resposta.body)
        assert corpo == {"dominio": "ti", "teto_tokens_diario": 1000, "tokens_hoje": 250}


class TestAtualizar:
    def _usuario(self, papeis: list[str]) -> dict:
        return {"sub": "1", "usuario": "teste", "papeis": papeis}

    def test_desenvolvedor_pode_alterar_qualquer_dominio(self, monkeypatch):
        gravados = []
        monkeypatch.setattr(
            mod.configuracoes_provedor, "definir_teto_tokens_diario", lambda dominio, valor: gravados.append((dominio, valor))
        )
        monkeypatch.setattr(mod.configuracoes_provedor, "teto_tokens_diario", lambda dominio: 500)
        monkeypatch.setattr(mod.auditoria_externa, "tokens_hoje", lambda dominio: 0)

        resposta = mod._atualizar("rh", self._usuario(["desenvolvedor"]), {"teto_tokens_diario": 500})

        assert resposta.status_code == 200
        assert gravados == [("rh", 500)]

    def test_admin_do_proprio_modulo_pode_alterar(self, monkeypatch):
        gravados = []
        monkeypatch.setattr(
            mod.configuracoes_provedor, "definir_teto_tokens_diario", lambda dominio, valor: gravados.append((dominio, valor))
        )
        monkeypatch.setattr(mod.configuracoes_provedor, "teto_tokens_diario", lambda dominio: 500)
        monkeypatch.setattr(mod.auditoria_externa, "tokens_hoje", lambda dominio: 0)

        resposta = mod._atualizar("rh", self._usuario(["rh_admin"]), {"teto_tokens_diario": 500})

        assert resposta.status_code == 200
        assert gravados == [("rh", 500)]

    def test_admin_de_outro_modulo_recebe_403(self, monkeypatch):
        gravados = []
        monkeypatch.setattr(
            mod.configuracoes_provedor, "definir_teto_tokens_diario", lambda dominio, valor: gravados.append((dominio, valor))
        )

        resposta = mod._atualizar("rh", self._usuario(["ti_admin"]), {"teto_tokens_diario": 500})

        assert resposta.status_code == 403
        assert gravados == []

    def test_usuario_comum_do_modulo_recebe_403(self, monkeypatch):
        gravados = []
        monkeypatch.setattr(
            mod.configuracoes_provedor, "definir_teto_tokens_diario", lambda dominio, valor: gravados.append((dominio, valor))
        )

        resposta = mod._atualizar("rh", self._usuario(["rh"]), {"teto_tokens_diario": 500})

        assert resposta.status_code == 403
        assert gravados == []

    def test_valor_invalido_devolve_400(self):
        resposta = mod._atualizar("rh", self._usuario(["desenvolvedor"]), {"teto_tokens_diario": -1})

        assert resposta.status_code == 400
