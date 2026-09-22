import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from agente_oracle.agent.ti import roteamento_chamado
from agente_oracle.server.ti.webhook_glpi import _autorizado, _chamado_id_do_payload, processar_webhook
from agente_oracle.tools.ti.categorias import CategoriaGlpi
from agente_oracle.tools.ti.glpi import Chamado

_SEGREDO = "x" * 32

# Mesmo motivo de `tests/unit/server/ti/test_chamados.py`: substitui as
# ~211 categorias reais por uma única categoria fake, pra não depender de
# similaridade de embedding de verdade num teste unitário.
_CATEGORIA_TESTE = CategoriaGlpi(999, "categoria de teste", "infra")


@pytest.fixture(autouse=True)
def _categoria_unica_para_teste(monkeypatch):
    monkeypatch.setattr("agente_oracle.tools.ti.categorias.CATEGORIAS_ATRIBUIVEIS", (_CATEGORIA_TESTE,))
    monkeypatch.setattr("agente_oracle.tools.ti.categorias.AREA_POR_CATEGORIA_ID", {999: "infra"})
    monkeypatch.setattr(roteamento_chamado, "_cache_embeddings_categorias", None)


@pytest.fixture(autouse=True)
def _roster_de_tecnicos_para_teste(monkeypatch):
    # Mesmo motivo de `test_chamados.py`: `escolher_tecnico`/
    # `todos_os_tecnicos` leem o roster do Postgres via
    # `listar_tecnicos_ti` — sem essa fixture, roster vazio estoura `min()`.
    # Cobre "processos" também — é `_AREA_PADRAO` de
    # `roteamento_chamado.py`, usada quando `usar_ia=False` e o chamado
    # não tem categoria nenhuma pra resolver área.
    roster = [
        {"usuario": "7", "nome": "Técnico Infra", "tecnico_glpi_id": "7", "area_ti": "infra"},
        {"usuario": "278", "nome": "Técnico Processos", "tecnico_glpi_id": "278", "area_ti": "processos"},
    ]
    monkeypatch.setattr("agente_oracle.tools.ti.tecnicos.listar_tecnicos_ti", lambda: roster)


def _chamado(id_: int = 1, categoria_id: int | None = None) -> Chamado:
    return Chamado(
        id=id_,
        titulo="Computador não liga",
        descricao="O computador do usuário apresenta o mesmo problema há alguns dias e precisa de atendimento técnico",
        categoria="Hardware",
        categoria_id=categoria_id,
        status="novo",
        solicitante="Solicitante",
        email="solicitante@empresa.com",
        avaliacao_mensagem=None,
        criado_em=datetime(2026, 1, 1, tzinfo=UTC),
        area=None,
        tecnico_atribuido=None,
    )


class _RespostaChatFake:
    def __init__(self, conteudo: str):
        self.message = type("Mensagem", (), {"content": conteudo})()


class _EmbedRespostaFake:
    def __init__(self, embedding: list[float]):
        self.embeddings = [embedding]


class _OllamaClienteFake:
    async def chat(self, **_kwargs):
        return _RespostaChatFake(json.dumps({"suficiente": True, "mensagem": ""}))

    async def embed(self, **_kwargs):
        return _EmbedRespostaFake([1.0, 0.0])


def _chat_nunca_chamado(**_kwargs):
    raise AssertionError("chat() não deveria ser chamado com usar_ia=False")


class _ClienteGLPIFake:
    """Implementação manual do Protocol `ClienteGLPI`, sem banco nem HTTP
    de verdade — mesmo padrão de `tests/unit/server/ti/test_chamados.py`."""

    def __init__(self, chamados: list[Chamado]):
        self._chamados = {chamado.id: chamado for chamado in chamados}
        self.atribuicoes: list[tuple[int, str, str]] = []

    async def listar(self) -> list[Chamado]:
        return list(self._chamados.values())

    async def buscar(self, chamado_id: int) -> Chamado | None:
        return self._chamados.get(chamado_id)

    async def atualizar_avaliacao(self, chamado_id: int, status: str, mensagem: str | None) -> None:
        self._chamados[chamado_id] = replace(
            self._chamados[chamado_id], status=status, avaliacao_mensagem=mensagem
        )

    async def atribuir(self, chamado_id: int, area: str, tecnico_identificador: str) -> None:
        self.atribuicoes.append((chamado_id, area, tecnico_identificador))
        self._chamados[chamado_id] = replace(
            self._chamados[chamado_id], area=area, tecnico_atribuido=tecnico_identificador
        )

    async def atualizar_categoria(self, chamado_id: int, categoria_id: int) -> None:
        self._chamados[chamado_id] = replace(self._chamados[chamado_id], categoria_id=categoria_id)

    async def carga_atual_por_tecnico(self, tecnicos_identificadores: list[str]) -> dict[str, int]:
        return dict.fromkeys(tecnicos_identificadores, 0)


class TestAutorizado:
    def test_segredo_certo_autoriza(self):
        assert _autorizado(_SEGREDO, _SEGREDO) is True

    def test_segredo_errado_nao_autoriza(self):
        assert _autorizado("outro-segredo", _SEGREDO) is False

    def test_segredo_ausente_nao_autoriza(self):
        assert _autorizado("", _SEGREDO) is False

    def test_segredo_esperado_vazio_nunca_autoriza_mesmo_sem_header(self):
        # GLPI_WEBHOOK_SECRET não configurado — sem essa checagem,
        # compare_digest("", "") daria True e qualquer chamada passaria.
        assert _autorizado("", "") is False

    def test_segredo_esperado_vazio_nao_autoriza_mesmo_com_algo_recebido(self):
        assert _autorizado("qualquer-coisa", "") is False


class TestChamadoIdDoPayload:
    def test_aceita_items_id(self):
        assert _chamado_id_do_payload({"items_id": 42}) == 42

    def test_aceita_id(self):
        assert _chamado_id_do_payload({"id": 42}) == 42

    def test_aceita_ticket_id(self):
        assert _chamado_id_do_payload({"ticket_id": 42}) == 42

    def test_aceita_string_numerica(self):
        assert _chamado_id_do_payload({"id": "42"}) == 42

    def test_payload_sem_nenhuma_chave_conhecida_devolve_none(self):
        assert _chamado_id_do_payload({"outra_coisa": 1}) is None

    def test_valor_nao_numerico_devolve_none_em_vez_de_levantar(self):
        assert _chamado_id_do_payload({"id": "não-é-numero"}) is None


class TestProcessarWebhook:
    async def test_payload_sem_id_devolve_400_e_nenhum_resultado(self):
        status_code, corpo, resultado = await processar_webhook(
            {}, _ClienteGLPIFake([]), _OllamaClienteFake(), "modelo-teste", True
        )
        assert status_code == 400
        assert resultado is None

    async def test_chamado_inexistente_devolve_404_e_nenhum_resultado(self):
        status_code, corpo, resultado = await processar_webhook(
            {"id": 999}, _ClienteGLPIFake([]), _OllamaClienteFake(), "modelo-teste", True
        )
        assert status_code == 404
        assert resultado is None

    async def test_chamado_existente_processa_e_devolve_200_com_resultado(self):
        # Categoria atual desconhecida (id 1 não está no mapa fake) —
        # dispara a classificação/correção normal (ver
        # tests/unit/server/ti/test_chamados.py pro caso sem categoria).
        cliente = _ClienteGLPIFake([_chamado(1, categoria_id=1)])

        status_code, corpo, resultado = await processar_webhook(
            {"id": 1}, cliente, _OllamaClienteFake(), "modelo-teste", True
        )

        assert status_code == 200
        assert corpo == {"ok": True}
        assert len(cliente.atribuicoes) == 1
        # `resultado` é o que `glpi_webhook_route` usa pra registrar em
        # `uso_ia_chamados` — aqui só confere que veio preenchido.
        assert resultado is not None
        assert resultado.avaliacao_suficiente is True
        assert resultado.precisou_embedding is True  # usar_ia=True sempre compara contra as categorias reais

    async def test_falha_no_processamento_ainda_devolve_200_sem_resultado(self):
        # "Retry storm" — o GLPI não deveria reenviar o evento por causa de
        # um erro interno nosso; /verificar (polling) cobre depois.
        # `resultado is None` aqui é esperado: a falha aconteceu antes de
        # `processar_chamado_novo` terminar, não tem o que logar.
        class _ClienteQueFalha(_ClienteGLPIFake):
            async def carga_atual_por_tecnico(self, tecnicos_identificadores):
                raise ConnectionError("Postgres fora do ar")

        status_code, corpo, resultado = await processar_webhook(
            {"id": 1}, _ClienteQueFalha([_chamado(1)]), _OllamaClienteFake(), "modelo-teste", True
        )

        assert status_code == 200
        assert corpo == {"ok": True}
        assert resultado is None

    async def test_usar_ia_false_nunca_chama_o_ollama(self):
        # Descrição com 15+ palavras passa na regra de suficiência sem
        # precisar do Ollama; "Computador não liga" já bate por regra de
        # área também.
        descricao_longa = (
            "O computador da recepção não liga desde ontem de manhã mesmo depois de trocar o cabo de força"
        )
        chamado = replace(_chamado(1), descricao=descricao_longa)
        cliente = _ClienteGLPIFake([chamado])
        ollama = _OllamaClienteFake()
        ollama.chat = _chat_nunca_chamado

        status_code, corpo, resultado = await processar_webhook(
            {"id": 1}, cliente, ollama, "modelo-teste", False
        )

        assert status_code == 200
        assert resultado is not None
        assert resultado.avaliacao_suficiente is True
