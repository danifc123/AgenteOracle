"""Smoke test de `tools/ti/protheus_login.py` contra o Protheus real
(homologação) — pula sozinho (em vez de falhar) se `PROTHEUS_DSN` não
estiver configurado ou o banco não responder, mesmo padrão de
`test_relatorios_stage.py` pro STAGE. Quem não tem VPN/acesso corporativo
continua rodando o resto da suíte normalmente.

Só leitura, mesma regra do módulo testado — nenhuma consulta aqui grava
ou altera nada no Protheus."""

import pytest

from agente_oracle.db.connection import DatabaseError, get_protheus_connection, protheus_configurado
from agente_oracle.tools.ti import protheus_login

pytestmark = pytest.mark.integration


def _protheus_disponivel() -> bool:
    if not protheus_configurado():
        return False
    try:
        with get_protheus_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT 1 FROM DUAL")
            cursor.fetchone()
        return True
    except DatabaseError:
        return False


@pytest.fixture(autouse=True)
def _requer_protheus():
    if not _protheus_disponivel():
        pytest.skip(
            "Protheus (login/auditoria) não está acessível — configure PROTHEUS_DSN/PROTHEUS_USER/"
            "PROTHEUS_PASSWORD no .env, com um usuário que só tenha SELECT nesse ambiente."
        )


class TestLoginsRecentes:
    def test_devolve_lista_com_o_formato_esperado(self):
        logins = protheus_login.logins_recentes(dias=7)
        assert isinstance(logins, list)
        for login in logins[:5]:
            assert set(login.keys()) == {"usuario", "data", "hora", "ip", "maquina"}


class TestTentativasBloqueioRecentes:
    def test_devolve_lista_com_o_formato_esperado_e_nunca_expoe_senha(self):
        tentativas = protheus_login.tentativas_bloqueio_recentes()
        assert isinstance(tentativas, list)
        for item in tentativas[:5]:
            assert set(item.keys()) == {"usuario", "bloqueado", "tentativas"}
