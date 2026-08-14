from agente_oracle.agent.ti import perfil_login as mod


def _login(usuario: str, ip: str = "1.1.1.1", maquina: str = "PC-1") -> dict:
    return {"usuario": usuario, "data": "20260212", "hora": "08:00:00", "ip": ip, "maquina": maquina}


def _bloqueio(usuario: str, bloqueado: bool = False, tentativas: int = 0) -> dict:
    return {"usuario": usuario, "bloqueado": bloqueado, "tentativas": tentativas}


class TestPerfilLoginsProtheus:
    def test_cruza_login_e_bloqueio_do_mesmo_usuario(self, monkeypatch):
        # `logins_recentes`/`tentativas_bloqueio_recentes` precisam devolver
        # `usuario` no MESMO formato pra `perfil_logins_protheus` conseguir
        # cruzar as duas fontes — é justamente o cruzamento que estava
        # quebrado (uma fonte usava USR_CODIGO, a outra USR_USERSOLOGON).
        usuario = "empresa.local@carlos.lima"
        monkeypatch.setattr(mod.protheus_login, "logins_recentes", lambda dias: [_login(usuario)])
        monkeypatch.setattr(
            mod.protheus_login,
            "tentativas_bloqueio_recentes",
            lambda: [_bloqueio(usuario, bloqueado=True, tentativas=5)],
        )

        [perfil] = mod.perfil_logins_protheus()

        assert perfil.usuario == usuario
        assert perfil.tentativas_bloqueio == 5
        assert perfil.bloqueado is True

    def test_usuario_sem_tentativa_de_bloqueio_fica_com_valores_zerados(self, monkeypatch):
        usuario = "empresa.local@ana.souza"
        monkeypatch.setattr(mod.protheus_login, "logins_recentes", lambda dias: [_login(usuario)])
        monkeypatch.setattr(mod.protheus_login, "tentativas_bloqueio_recentes", lambda: [])

        [perfil] = mod.perfil_logins_protheus()

        assert perfil.tentativas_bloqueio == 0
        assert perfil.bloqueado is False

    def test_conta_ips_e_maquinas_distintas(self, monkeypatch):
        usuario = "empresa.local@carlos.lima"
        logins = [
            _login(usuario, ip="10.0.0.5", maquina="PC-DESCONHECIDO-1"),
            _login(usuario, ip="187.45.12.9", maquina="NOTEBOOK-EXTERNO"),
            _login(usuario, ip="10.0.0.5", maquina="PC-DESCONHECIDO-1"),
        ]
        monkeypatch.setattr(mod.protheus_login, "logins_recentes", lambda dias: logins)
        monkeypatch.setattr(mod.protheus_login, "tentativas_bloqueio_recentes", lambda: [])

        [perfil] = mod.perfil_logins_protheus()

        assert perfil.total_logins == 3
        assert perfil.ips_distintos == 2
        assert perfil.maquinas_distintas == 2

    def test_sem_logins_devolve_lista_vazia(self, monkeypatch):
        monkeypatch.setattr(mod.protheus_login, "logins_recentes", lambda dias: [])
        monkeypatch.setattr(mod.protheus_login, "tentativas_bloqueio_recentes", lambda: [])

        assert mod.perfil_logins_protheus() == []
