"""Testa só a fiação do app real (`criar_app`) que não cabe em nenhum
outro teste específico — hoje, o poller em background da Auditoria de
Chamados (`server/ti/chamados.py::iniciar_poller_verificar_chamados`).
Usa um stub no lugar do poller de verdade: o teste não pode disparar uma
chamada real ao GLPI/Ollama só de subir o app."""

from starlette.testclient import TestClient

from agente_oracle.server import app as app_module
from agente_oracle.server.app import criar_app


class TestPollerNoStartup:
    def test_startup_dispara_o_poller_sem_quebrar_o_lifespan_original(self, monkeypatch):
        chamadas = []

        async def _poller_fake():
            chamadas.append("chamou")

        monkeypatch.setattr(app_module.ti.chamados, "iniciar_poller_verificar_chamados", _poller_fake)

        with TestClient(criar_app()) as cliente:
            # `with` dispara o protocolo de lifespan (startup) de verdade —
            # sem isso, nenhum evento de startup roda (ver test_cors.py,
            # que usa sem `with` de propósito, pra não disparar isso).
            resposta = cliente.get("/api/auth/papeis")

        assert resposta.status_code in (200, 401, 403)  # não é 500 — o app subiu normal
        assert chamadas == ["chamou"]
