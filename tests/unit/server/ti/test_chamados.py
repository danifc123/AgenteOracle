import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from agente_oracle.agent.ti import roteamento_chamado
from agente_oracle.server.ti.chamados import processar_chamado_novo
from agente_oracle.tools.ti.categorias import CategoriaGlpi
from agente_oracle.tools.ti.glpi import Chamado

# `classificar_categoria` compara contra as ~211 categorias reais — pesado
# e não-determinístico de mais pra um teste unitário. Substitui por uma
# única categoria fake, então a "melhor categoria" é sempre ela, sem
# depender de nenhuma lógica de similaridade de verdade.
_CATEGORIA_TESTE = CategoriaGlpi(999, "categoria de teste", "infra")


@pytest.fixture(autouse=True)
def _categoria_unica_para_teste(monkeypatch):
    monkeypatch.setattr("agente_oracle.tools.ti.categorias.CATEGORIAS_ATRIBUIVEIS", (_CATEGORIA_TESTE,))
    monkeypatch.setattr("agente_oracle.tools.ti.categorias.AREA_POR_CATEGORIA_ID", {999: "infra"})
    monkeypatch.setattr(roteamento_chamado, "_cache_embeddings_categorias", None)


def _chamado(
    id_: int = 1,
    titulo: str = "Computador não liga",
    descricao: str = "detalhe",
    categoria: str = "Hardware",
    categoria_id: int | None = None,
) -> Chamado:
    return Chamado(
        id=id_,
        titulo=titulo,
        descricao=descricao,
        categoria=categoria,
        categoria_id=categoria_id,
        status="novo",
        solicitante="Solicitante",
        email="solicitante@empresa.com",
        avaliacao_mensagem=None,
        reportado_em=None,
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
    """`processar_chamado_novo` usa `chat(...)` (via `avaliar_chamado`) e
    `embed(...)` (via `classificar_categoria`, sempre que `usar_ia=True` —
    não tem mais regra por palavra-chave que dispense o embedding)."""

    def __init__(self, suficiente: bool = True, mensagem: str = ""):
        self._suficiente = suficiente
        self._mensagem = mensagem

    async def chat(self, **_kwargs):
        return _RespostaChatFake(json.dumps({"suficiente": self._suficiente, "mensagem": self._mensagem}))

    async def embed(self, **_kwargs):
        return _EmbedRespostaFake([1.0, 0.0])


def _chat_nunca_chamado(**_kwargs):
    raise AssertionError("chat() não deveria ser chamado com usar_ia=False")


class _ClienteGLPIFake:
    """Implementação manual do Protocol `ClienteGLPI`, sem banco nem HTTP
    de verdade — só guarda o que foi chamado, pra inspecionar no `assert`."""

    def __init__(self, chamados: list[Chamado]):
        self._chamados = {chamado.id: chamado for chamado in chamados}
        self.atribuicoes: list[tuple[int, str, str]] = []
        self.avaliacoes: list[tuple[int, str, str | None]] = []
        self.categorias_atualizadas: list[tuple[int, int]] = []

    async def listar(self) -> list[Chamado]:
        return list(self._chamados.values())

    async def buscar(self, chamado_id: int) -> Chamado | None:
        return self._chamados.get(chamado_id)

    async def atualizar_avaliacao(self, chamado_id: int, status: str, mensagem: str | None) -> None:
        self.avaliacoes.append((chamado_id, status, mensagem))
        self._chamados[chamado_id] = replace(
            self._chamados[chamado_id], status=status, avaliacao_mensagem=mensagem
        )

    async def atribuir(self, chamado_id: int, area: str, tecnico_identificador: str) -> None:
        self.atribuicoes.append((chamado_id, area, tecnico_identificador))
        self._chamados[chamado_id] = replace(
            self._chamados[chamado_id], area=area, tecnico_atribuido=tecnico_identificador
        )

    async def atualizar_categoria(self, chamado_id: int, categoria_id: int) -> None:
        self.categorias_atualizadas.append((chamado_id, categoria_id))
        self._chamados[chamado_id] = replace(self._chamados[chamado_id], categoria_id=categoria_id)

    async def carga_atual_por_tecnico(self, tecnicos_identificadores: list[str]) -> dict[str, int]:
        return dict.fromkeys(tecnicos_identificadores, 0)

    async def reportar_usuario(self, chamado_id: int) -> None:
        self._chamados[chamado_id] = replace(self._chamados[chamado_id], reportado_em=datetime.now(UTC))


class TestProcessarChamadoNovo:
    async def test_chamado_insuficiente_fica_aguardando_usuario_sem_atribuir(self):
        cliente = _ClienteGLPIFake([_chamado()])
        ollama = _OllamaClienteFake(suficiente=False, mensagem="Qual sistema está afetado?")
        cargas: dict[str, int] = {}

        resultado = await processar_chamado_novo(cliente, ollama, "modelo-teste", _chamado(), cargas, True)

        assert cliente.avaliacoes == [(1, "aguardando_usuario", "Qual sistema está afetado?")]
        assert cliente.atribuicoes == []
        assert cargas == {}
        assert resultado.avaliacao_suficiente is False
        assert resultado.precisou_embedding is None  # nem chegou a classificar_categoria

    async def test_chamado_sem_categoria_insuficiente_fica_aguardando_usuario_normal(self):
        # Chamado por e-mail (sem categoria) com conteúdo insuficiente
        # segue o fluxo normal — só o caso suficiente é tratado à parte.
        cliente = _ClienteGLPIFake([_chamado(categoria_id=None)])
        ollama = _OllamaClienteFake(suficiente=False, mensagem="Qual sistema está afetado?")
        cargas: dict[str, int] = {}

        resultado = await processar_chamado_novo(
            cliente, ollama, "modelo-teste", _chamado(categoria_id=None), cargas, True
        )

        assert cliente.avaliacoes == [(1, "aguardando_usuario", "Qual sistema está afetado?")]
        assert resultado.avaliacao_suficiente is False

    async def test_chamado_sem_categoria_suficiente_nao_escreve_nada_no_glpi(self):
        # Chamado por e-mail (sem categoria) — confirmado com o
        # responsável do GLPI que já entra direto na fila de TI. Sem
        # categoria pra corrigir nem base pra escolher técnico, então só
        # confirma que tem informação suficiente e não mexe em nada (não
        # atribui técnico, não marca `fila_atendimento` — evitar marcar
        # "Em atendimento" sem ninguém de fato atribuído no GLPI real).
        cliente = _ClienteGLPIFake([_chamado(categoria_id=None)])
        ollama = _OllamaClienteFake(suficiente=True)
        cargas: dict[str, int] = {}

        resultado = await processar_chamado_novo(
            cliente, ollama, "modelo-teste", _chamado(categoria_id=None), cargas, True
        )

        assert cliente.avaliacoes == []
        assert cliente.atribuicoes == []
        assert cliente.categorias_atualizadas == []
        assert cargas == {}
        assert resultado.avaliacao_suficiente is True
        assert resultado.precisou_embedding is False

    async def test_chamado_suficiente_classifica_atribui_e_vai_pra_fila(self):
        # Categoria atual desconhecida (id 1 não está no mapa fake) — a
        # única categoria fake ("infra", id 999) sempre vence e sempre
        # precisa ser gravada no GLPI.
        cliente = _ClienteGLPIFake([_chamado(categoria_id=1)])
        ollama = _OllamaClienteFake(suficiente=True)
        cargas = {"tecnico1": 0}

        resultado = await processar_chamado_novo(
            cliente, ollama, "modelo-teste", _chamado(categoria_id=1), cargas, True
        )

        assert len(cliente.atribuicoes) == 1
        chamado_id, area, _tecnico = cliente.atribuicoes[0]
        assert chamado_id == 1
        assert area == "infra"
        assert cliente.categorias_atualizadas == [(1, 999)]
        assert cliente.avaliacoes == [(1, "fila_atendimento", None)]
        assert resultado.avaliacao_suficiente is True
        assert resultado.precisou_embedding is True

    async def test_categoria_atual_ja_correta_nao_reescreve_categoria(self):
        cliente = _ClienteGLPIFake([_chamado(categoria_id=999)])
        ollama = _OllamaClienteFake(suficiente=True)
        cargas = {"tecnico1": 0}

        await processar_chamado_novo(
            cliente, ollama, "modelo-teste", _chamado(categoria_id=999), cargas, True
        )

        assert cliente.categorias_atualizadas == []

    async def test_atribuir_incrementa_a_carga_do_tecnico_escolhido(self):
        # Relevante pra processar um lote: a 2a chamada dentro do mesmo
        # `chamados_verificar_route` já vê a carga da 1a, mesmo antes de
        # qualquer uma das duas ter sido de fato salva no GLPI/mock.
        cliente = _ClienteGLPIFake([_chamado(categoria_id=1)])
        ollama = _OllamaClienteFake(suficiente=True)
        cargas: dict[str, int] = {}

        await processar_chamado_novo(cliente, ollama, "modelo-teste", _chamado(categoria_id=1), cargas, True)

        _chamado_id, _area, tecnico = cliente.atribuicoes[0]
        assert cargas[tecnico] == 1

    async def test_usar_ia_false_nunca_chama_o_ollama_e_ainda_assim_classifica(self):
        # Descrição com 15+ palavras passa na regra de suficiência.
        # Categoria atual já conhecida (999 -> "infra") — com usar_ia=False
        # `classificar_categoria` usa essa área direto, sem chamar Ollama.
        descricao_longa = (
            "O computador da recepção não liga desde ontem de manhã mesmo depois de trocar o cabo de força"
        )
        chamado = _chamado(descricao=descricao_longa, categoria_id=999)
        cliente = _ClienteGLPIFake([chamado])
        ollama = _OllamaClienteFake()
        ollama.chat = _chat_nunca_chamado
        cargas: dict[str, int] = {}

        resultado = await processar_chamado_novo(cliente, ollama, "modelo-teste", chamado, cargas, False)

        assert resultado.avaliacao_suficiente is True
        assert len(cliente.atribuicoes) == 1
