"""Testa o CORS de ponta a ponta com o app real (`criar_app`, o mesmo usado
em produção via `main()`), não o app "pelado" que a fixture `mcp_app` dos
testes de integração usa — aquela nunca passa pelo `CORSMiddleware`, então
não serviria pra flagrar a falha que este teste cobre: antes, toda rota
espalhava `Access-Control-Allow-Origin: *` (`server/cors.py`) por conta
própria, e isso só era sobrescrito pelo `CORSMiddleware` quando a origem da
requisição já estava na lista permitida — pra uma origem QUALQUER fora da
lista, o `*` da rota ficava intocado, ou seja, a restrição nunca valia de
verdade pra ninguém de fora."""

from starlette.testclient import TestClient

from agente_oracle.config import settings
from agente_oracle.server.app import criar_app


class TestCorsMiddleware:
    def test_origem_permitida_recebe_o_header_com_a_propria_origem(self):
        origem_permitida = settings.allowed_origins_list[0]
        cliente = TestClient(criar_app())

        resposta = cliente.get("/api/auth/papeis", headers={"Origin": origem_permitida})

        assert resposta.headers.get("access-control-allow-origin") == origem_permitida

    def test_origem_nao_permitida_nao_recebe_o_header(self):
        cliente = TestClient(criar_app())

        resposta = cliente.get("/api/auth/papeis", headers={"Origin": "https://site-malicioso.example"})

        assert "access-control-allow-origin" not in resposta.headers

    def test_sem_header_origin_nao_ativa_o_cors(self):
        """Requisição sem `Origin` (ex: chamada servidor-a-servidor, curl,
        Postman) não é uma requisição CORS de verdade — o middleware nem
        processa esse caso, e a resposta não deve carregar o header."""
        cliente = TestClient(criar_app())

        resposta = cliente.get("/api/auth/papeis")

        assert "access-control-allow-origin" not in resposta.headers