from starlette.testclient import TestClient

from agente_oracle.server.app import criar_app


class TestHeadersDeSeguranca:
    def test_resposta_carrega_os_headers_padrao(self):
        cliente = TestClient(criar_app())

        resposta = cliente.get("/api/auth/papeis")

        assert resposta.headers.get("x-content-type-options") == "nosniff"
        assert resposta.headers.get("x-frame-options") == "DENY"
        assert resposta.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        assert "default-src 'none'" in resposta.headers.get("content-security-policy", "")
        assert "max-age=" in resposta.headers.get("strict-transport-security", "")

    def test_headers_aparecem_mesmo_em_resposta_de_erro(self):
        """A rota nem existe (404) — os headers de segurança têm que estar
        presentes independente do status da resposta."""
        cliente = TestClient(criar_app())

        resposta = cliente.get("/rota/que/nao/existe")

        assert resposta.headers.get("x-content-type-options") == "nosniff"
