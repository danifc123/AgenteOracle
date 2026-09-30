"""Testa `/api/auth/cores-ambiente` de ponta a ponta contra o Postgres de
teste — autoatendimento aberto a qualquer usuário autenticado (mesmo
`usuario_teste`/`token_teste` compartilhados, papel `financeiro`, usados só
porque já existem no `conftest.py`; a rota em si não checa módulo nenhum,
ver `server/auth/cores_ambiente.py`)."""

import uuid

import pytest

from agente_oracle.tools.auth import cores_ambiente

pytestmark = pytest.mark.integration


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestRotaCoresAmbiente:
    def test_sem_token_e_nao_autorizado(self, mcp_app):
        resposta = mcp_app.get("/api/auth/cores-ambiente")
        assert resposta.status_code == 401

    def test_lista_vazia_quando_nada_personalizado(self, mcp_app, token_teste):
        resposta = mcp_app.get("/api/auth/cores-ambiente", headers=_auth(token_teste))
        assert resposta.status_code == 200
        assert resposta.json() == []

    def test_definir_uma_cor_e_ela_aparece_na_listagem(self, mcp_app, token_teste):
        resposta = mcp_app.put(
            "/api/auth/cores-ambiente/--color-primary", json={"cor": "#123456"}, headers=_auth(token_teste)
        )
        assert resposta.status_code == 200
        assert resposta.json() == {"token": "--color-primary", "cor": "#123456"}

        resposta = mcp_app.get("/api/auth/cores-ambiente", headers=_auth(token_teste))
        assert resposta.json() == [{"token": "--color-primary", "cor": "#123456"}]

    def test_definir_de_novo_atualiza_em_vez_de_duplicar(self, mcp_app, token_teste):
        mcp_app.put("/api/auth/cores-ambiente/--color-accent", json={"cor": "#111111"}, headers=_auth(token_teste))
        mcp_app.put("/api/auth/cores-ambiente/--color-accent", json={"cor": "#222222"}, headers=_auth(token_teste))

        resposta = mcp_app.get("/api/auth/cores-ambiente", headers=_auth(token_teste))
        linhas = [linha for linha in resposta.json() if linha["token"] == "--color-accent"]
        assert linhas == [{"token": "--color-accent", "cor": "#222222"}]

    def test_token_fora_da_lista_permitida_e_rejeitado(self, mcp_app, token_teste):
        resposta = mcp_app.put(
            "/api/auth/cores-ambiente/--color-nao-existe", json={"cor": "#ff0000"}, headers=_auth(token_teste)
        )
        assert resposta.status_code == 400

    def test_token_rgba_com_transparencia_e_rejeitado(self, mcp_app, token_teste):
        # `--color-error-soft`/`--color-warning-soft`/`--color-success-soft`
        # ficam de fora de propósito — são `rgba(...)` (ou alias de um que
        # é), o `<input type="color">` do frontend não representa
        # transparência (ver `_TOKENS_VALIDOS`).
        resposta = mcp_app.put(
            "/api/auth/cores-ambiente/--color-error-soft", json={"cor": "#ff0000"}, headers=_auth(token_teste)
        )
        assert resposta.status_code == 400

    def test_cor_vazia_e_rejeitada(self, mcp_app, token_teste):
        resposta = mcp_app.put("/api/auth/cores-ambiente/--color-primary", json={"cor": ""}, headers=_auth(token_teste))
        assert resposta.status_code == 400

    def test_redefinir_remove_a_cor_personalizada(self, mcp_app, token_teste):
        mcp_app.put("/api/auth/cores-ambiente/--color-primary", json={"cor": "#123456"}, headers=_auth(token_teste))

        resposta = mcp_app.delete("/api/auth/cores-ambiente/--color-primary", headers=_auth(token_teste))
        assert resposta.status_code == 200

        resposta = mcp_app.get("/api/auth/cores-ambiente", headers=_auth(token_teste))
        assert resposta.json() == []

    def test_cores_de_um_usuario_nao_aparecem_pra_outro(self, mcp_app, token_teste, token_dev):
        mcp_app.put("/api/auth/cores-ambiente/--color-primary", json={"cor": "#abcdef"}, headers=_auth(token_teste))

        resposta = mcp_app.get("/api/auth/cores-ambiente", headers=_auth(token_dev))
        assert resposta.json() == []


class TestApagarUsuarioLimpaCoresAmbiente:
    def test_deletar_usuario_remove_cores_personalizadas(self):
        from agente_oracle.tools.auth import usuarios as usuarios_tools

        login = f"teste_apagar_cores_{uuid.uuid4().hex[:12]}"
        criado = usuarios_tools.criar_usuario(login, "SenhaDeTeste!123", "Apagar (teste)", ["financeiro"])
        cores_ambiente.definir(criado["id"], "--color-primary", "#123456")
        assert cores_ambiente.listar(criado["id"]) == [{"token": "--color-primary", "cor": "#123456"}]

        usuarios_tools.deletar_usuario(criado["id"])

        assert cores_ambiente.listar(criado["id"]) == []
