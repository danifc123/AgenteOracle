"""Testa `GET /api/ti/chamados/meus-indicadores` — o cliente GLPI é
fakeado (`monkeypatch` em `chamados_module._cliente`), já que não dá pra
depender da instância real ter chamados/tempo registrado o bastante pra
um teste determinístico; o roster de técnicos usa o Postgres de teste de
verdade (mesmo padrão de `test_tecnicos_ti.py`)."""

import uuid
from datetime import UTC, datetime

import pytest

from agente_oracle.server.ti import chamados as chamados_module
from agente_oracle.tools.ti.glpi import Chamado

pytestmark = pytest.mark.integration

_URL = "/api/ti/chamados/meus-indicadores"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _chamado(id_: int, tecnico_atribuido: str | None, tempo_gasto_segundos: int = 0) -> Chamado:
    return Chamado(
        id=id_,
        titulo="Chamado de teste",
        descricao="",
        categoria="",
        categoria_id=None,
        status="novo",
        solicitante="",
        email="",
        avaliacao_mensagem=None,
        criado_em=datetime.now(UTC),
        area=None,
        tecnico_atribuido=tecnico_atribuido,
        tempo_gasto_segundos=tempo_gasto_segundos,
    )


class _ClienteGLPIFakeIndicadores:
    """Duck-typed de propósito (só o método que esta rota chama) — o
    `ClienteGLPI` completo (`tests/unit/server/ti/test_chamados.py::
    _ClienteGLPIFake`) é overkill pra testar só esta rota."""

    def __init__(self, chamados: list[Chamado]):
        self._chamados = chamados

    async def chamados_criados_desde(self, desde: datetime) -> list[Chamado]:
        return self._chamados


@pytest.fixture
def dois_tecnicos(mcp_app):
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login_a = f"teste_tecnico_ind_a_{uuid.uuid4().hex[:12]}"
    login_b = f"teste_tecnico_ind_b_{uuid.uuid4().hex[:12]}"
    senha = "SenhaDeTeste!123"
    criado_a = usuarios_tools.criar_usuario(
        login_a, senha, "Técnico A (teste)", ["ti_infraestrutura"], tecnico_glpi_id="601", area_ti="infra"
    )
    criado_b = usuarios_tools.criar_usuario(
        login_b, senha, "Técnico B (teste)", ["ti_sistemas"], tecnico_glpi_id="602", area_ti="sistemas"
    )
    try:
        resposta_a = mcp_app.post("/api/auth/login", json={"usuario": login_a, "senha": senha})
        resposta_b = mcp_app.post("/api/auth/login", json={"usuario": login_b, "senha": senha})
        assert resposta_a.status_code == 200
        assert resposta_b.status_code == 200
        yield {
            "token_a": resposta_a.json()["token"],
            "token_b": resposta_b.json()["token"],
        }
    finally:
        usuarios_tools.deletar_usuario(criado_a["id"])
        usuarios_tools.deletar_usuario(criado_b["id"])


def _medias_esperadas(total_chamados: int, total_segundos: int) -> tuple[float, float]:
    # O roster (`todos_os_tecnicos`) lê o Postgres de teste de verdade —
    # pode ter outros técnicos além dos 2 desta fixture — a média precisa
    # ser calculada contra o tamanho REAL do roster no momento do teste.
    from agente_oracle.tools.auth.usuarios import listar_tecnicos_ti

    quantidade_tecnicos = len(listar_tecnicos_ti())
    return (
        round(total_chamados / quantidade_tecnicos, 1),
        round(total_segundos / quantidade_tecnicos / 3600, 1),
    )


def test_tecnico_abaixo_da_media_nos_dois_indicadores(mcp_app, monkeypatch, dois_tecnicos):
    # Técnico A (601) pega 1 chamado com 1h; técnico B (602) pega 5
    # chamados com 2h cada (10h) — A fica abaixo nos dois indicadores.
    chamados = [
        _chamado(1, "601", tempo_gasto_segundos=3600),
        *[_chamado(i, "602", tempo_gasto_segundos=7200) for i in range(2, 7)],
    ]
    monkeypatch.setattr(chamados_module, "_cliente", _ClienteGLPIFakeIndicadores(chamados))

    resposta = mcp_app.get(_URL, headers=_auth(dois_tecnicos["token_a"]))

    assert resposta.status_code == 200
    corpo = resposta.json()
    media_chamados, media_tempo = _medias_esperadas(total_chamados=6, total_segundos=3600 + 5 * 7200)
    assert corpo["meus_chamados"] == 1
    assert corpo["media_chamados_equipe"] == media_chamados
    assert corpo["meu_tempo_gasto_horas"] == 1.0
    assert corpo["media_tempo_gasto_equipe_horas"] == media_tempo
    assert corpo["meus_chamados"] < corpo["media_chamados_equipe"]
    assert corpo["meu_tempo_gasto_horas"] < corpo["media_tempo_gasto_equipe_horas"]


def test_tecnico_acima_da_media_nos_dois_indicadores(mcp_app, monkeypatch, dois_tecnicos):
    chamados = [
        _chamado(1, "601", tempo_gasto_segundos=3600),
        *[_chamado(i, "602", tempo_gasto_segundos=7200) for i in range(2, 7)],
    ]
    monkeypatch.setattr(chamados_module, "_cliente", _ClienteGLPIFakeIndicadores(chamados))

    resposta = mcp_app.get(_URL, headers=_auth(dois_tecnicos["token_b"]))

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["meus_chamados"] == 5
    assert corpo["meu_tempo_gasto_horas"] == 10.0
    assert corpo["meus_chamados"] > corpo["media_chamados_equipe"]
    assert corpo["meu_tempo_gasto_horas"] > corpo["media_tempo_gasto_equipe_horas"]


def test_chamado_sem_tempo_registrado_nao_quebra_a_media_de_tempo(mcp_app, monkeypatch, dois_tecnicos):
    # Cenário real de homologação: `actiontime` sempre 0 — a média de
    # tempo sai 0.0, não erro/None.
    chamados = [_chamado(1, "601", tempo_gasto_segundos=0)]
    monkeypatch.setattr(chamados_module, "_cliente", _ClienteGLPIFakeIndicadores(chamados))

    resposta = mcp_app.get(_URL, headers=_auth(dois_tecnicos["token_a"]))

    assert resposta.status_code == 200
    assert resposta.json()["meu_tempo_gasto_horas"] == 0.0


def test_usuario_sem_tecnico_vinculado_recebe_os_dois_campos_meu_null(mcp_app, monkeypatch, token_dev):
    # `desenvolvedor` tem acesso ao módulo TI (acesso_total), mas o
    # usuário de teste não tem `tecnico_glpi_id` vinculado — exatamente o
    # caso que os campos `null` existem pra cobrir.
    monkeypatch.setattr(chamados_module, "_cliente", _ClienteGLPIFakeIndicadores([]))

    resposta = mcp_app.get(_URL, headers=_auth(token_dev))

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["meus_chamados"] is None
    assert corpo["meu_tempo_gasto_horas"] is None


def test_usuario_sem_modulo_ti_recebe_403(mcp_app, token_teste):
    resposta = mcp_app.get(_URL, headers=_auth(token_teste))

    assert resposta.status_code == 403
