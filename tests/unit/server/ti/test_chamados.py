import json
from dataclasses import replace
from datetime import UTC, datetime

import psycopg
import pytest

from agente_oracle.agent.ti import roteamento_chamado
from agente_oracle.agent.ti.qualidade_chamado import TurnoConversa
from agente_oracle.config import settings
from agente_oracle.server.ti import chamados as chamados_module
from agente_oracle.server.ti.chamados import (
    _chamados_da_tela,
    _saude_por_area,
    _texto_para_ia,
    chamado_entra_na_amostra,
    processar_chamado_novo,
    verificar_chamados_aguardando_resposta,
    verificar_chamados_pendentes,
)
from agente_oracle.tools.ia.cliente_openai_compativel import EmbeddingNaoSuportado
from agente_oracle.tools.ti import uso_ia_chamados
from agente_oracle.tools.ti.categorias import CategoriaGlpi
from agente_oracle.tools.ti.glpi import Chamado, Followup
from agente_oracle.tools.ti.tecnicos import SemTecnicoNaArea, Tecnico

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


@pytest.fixture(autouse=True)
def _roster_de_tecnicos_para_teste(monkeypatch):
    # `escolher_tecnico`/`todos_os_tecnicos` (tools/ti/tecnicos.py) leem o
    # roster do Postgres via `listar_tecnicos_ti` — sem essa fixture, um
    # teste unitário sem banco real cairia num roster vazio e `min()`
    # estouraria. `"7"` mantém compatibilidade com os testes que já
    # fixam esse id (herdado de quando o roster era a tupla fixa).
    roster = [
        {"usuario": "7", "nome": "Técnico Infra", "tecnico_glpi_id": "7", "area_ti": "infra"},
        {"usuario": "8", "nome": "Técnico Sistemas", "tecnico_glpi_id": "8", "area_ti": "sistemas"},
        {"usuario": "278", "nome": "Técnico Processos", "tecnico_glpi_id": "278", "area_ti": "processos"},
    ]
    monkeypatch.setattr("agente_oracle.tools.ti.tecnicos.listar_tecnicos_ti", lambda: roster)


@pytest.fixture(autouse=True)
def _amostragem_liberada_por_padrao(monkeypatch):
    # Sem isso a amostragem leria o Postgres e, falhando, nenhum chamado seria processado.
    monkeypatch.setattr(
        chamados_module.amostragem_chamados, "deve_analisar", lambda _id, _criado_em=None: True
    )


_DESCRICAO_PADRAO_TESTE = (
    "O computador do usuário apresenta o mesmo problema há alguns dias e precisa de atendimento técnico"
)


def _chamado(
    id_: int = 1,
    titulo: str = "Computador não liga",
    descricao: str = _DESCRICAO_PADRAO_TESTE,
    categoria: str = "Hardware",
    categoria_id: int | None = None,
    tecnico_atribuido: str | None = None,
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
        criado_em=datetime(2026, 1, 1, tzinfo=UTC),
        area=None,
        tecnico_atribuido=tecnico_atribuido,
    )


def _followups_ciclo(rodadas: int) -> list[Followup]:
    """`rodadas` pares (pergunta da IA, resposta do solicitante) — usado
    pra simular um chamado que já passou por N rodadas de esclarecimento
    antes desta avaliação. `autor_nome == settings.glpi_username` é o
    sinal que `_turnos_da_conversa` usa pra reconhecer "isso foi a IA"."""
    followups = []
    for indice in range(rodadas):
        followups.append(
            Followup(
                autor_id=274,
                autor_nome=settings.glpi_username,
                conteudo=f"Pergunta {indice + 1} da IA",
                criado_em=datetime(2026, 1, indice + 1, 10, tzinfo=UTC),
            )
        )
        followups.append(
            Followup(
                autor_id=999,
                autor_nome="solicitante.teste",
                conteudo=f"Resposta {indice + 1} do solicitante",
                criado_em=datetime(2026, 1, indice + 1, 11, tzinfo=UTC),
            )
        )
    return followups


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

    def __init__(self, suficiente: bool = True, mensagem: str = "", levantar_no_embed: Exception | None = None):
        self._suficiente = suficiente
        self._mensagem = mensagem
        self._levantar_no_embed = levantar_no_embed
        self.chamadas_chat: list[dict] = []

    async def chat(self, **kwargs):
        self.chamadas_chat.append(kwargs)
        return _RespostaChatFake(json.dumps({"suficiente": self._suficiente, "mensagem": self._mensagem}))

    async def embed(self, **_kwargs):
        if self._levantar_no_embed:
            raise self._levantar_no_embed
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
        self.followups_por_chamado: dict[int, list[Followup]] = {}
        self.usuarios_atribuidos: list[tuple[int, str]] = []
        self.usuarios_desatribuidos: list[tuple[int, str]] = []

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

    async def buscar_followups(self, chamado_id: int) -> list[Followup]:
        return self.followups_por_chamado.get(chamado_id, [])

    async def atribuir_usuario(self, chamado_id: int, usuario_id: str) -> None:
        self.usuarios_atribuidos.append((chamado_id, usuario_id))
        self._chamados[chamado_id] = replace(self._chamados[chamado_id], tecnico_atribuido=usuario_id)

    async def desatribuir_usuario(self, chamado_id: int, usuario_id: str) -> None:
        self.usuarios_desatribuidos.append((chamado_id, usuario_id))
        self._chamados[chamado_id] = replace(self._chamados[chamado_id], tecnico_atribuido=None)

    async def baixar_documento(self, documento_id: int) -> None:
        return None

    async def buscar_tecnicos_disponiveis(self) -> list:
        return []

    async def buscar_area_do_tecnico(self, usuario_id: str) -> None:
        return None


class TestPerguntaParecidaComAlgumaAnterior:
    def test_pergunta_praticamente_repetida_e_detectada(self):
        # Caso real, chamado #3340 (2026-09-25): a IA perguntou de novo,
        # com outras palavras, algo que já tinha perguntado antes.
        anterior = (
            'Qual é o comportamento exato quando tenta abrir as pastas do módulo financeiro? Por '
            'exemplo: ao clicar no módulo financeiro, aparece a mensagem "Acesso negado" ou a tela '
            "fica em branco sem carregar as pastas."
        )
        nova = (
            "Você poderia especificar o que acontece exatamente ao tentar abrir o módulo financeiro? "
            "Por exemplo: aparece alguma mensagem de erro, a tela fica em branco ou o sistema não "
            "responde ao clique."
        )
        turnos = [TurnoConversa(papel="ia", conteudo=anterior)]

        assert chamados_module._pergunta_parecida_com_alguma_anterior(nova, turnos) is True

    def test_pergunta_genuinamente_diferente_nao_e_marcada(self):
        turnos = [
            TurnoConversa(
                papel="ia",
                conteudo="Desde quando você está enfrentando esse problema ao tentar visualizar as pastas?",
            )
        ]
        nova = (
            'Qual é o comportamento exato quando tenta abrir as pastas do módulo financeiro? Por '
            'exemplo: ao clicar, aparece a mensagem "Acesso negado" ou a tela fica em branco?'
        )

        assert chamados_module._pergunta_parecida_com_alguma_anterior(nova, turnos) is False

    def test_ignora_turnos_do_usuario_na_comparacao(self):
        # Só compara contra perguntas da PRÓPRIA IA — a resposta do
        # usuário pode compartilhar palavras com a pergunta nova sem que
        # isso seja repetição nenhuma.
        turnos = [TurnoConversa(papel="usuario", conteudo="Qual é o comportamento exato do módulo financeiro?")]
        nova = "Qual é o comportamento exato do módulo financeiro?"

        assert chamados_module._pergunta_parecida_com_alguma_anterior(nova, turnos) is False

    def test_sem_turnos_anteriores_nunca_e_repetitiva(self):
        assert chamados_module._pergunta_parecida_com_alguma_anterior("Qual sistema é afetado?", []) is False


class TestProcessarChamadoNovo:
    async def test_chamado_insuficiente_fica_aguardando_usuario_sem_atribuir(self):
        cliente = _ClienteGLPIFake([_chamado()])
        ollama = _OllamaClienteFake(suficiente=False, mensagem="Qual sistema está afetado?")
        cargas: dict[str, int] = {}

        resultado = await processar_chamado_novo(cliente, ollama, "modelo-teste", _chamado(), cargas, True)

        assert cliente.avaliacoes == [(1, "aguardando_usuario", "Qual sistema está afetado?")]
        assert cliente.atribuicoes == []  # nenhum técnico "de negócio" atribuído
        assert cargas == {}
        assert resultado.avaliacao_suficiente is False
        assert resultado.precisou_embedding is None  # nem chegou a classificar_categoria

    async def test_chamado_insuficiente_pela_primeira_vez_atribui_a_conta_da_ia(self, monkeypatch):
        # GLPI rejeita silenciosamente troca de status sem ninguém
        # atribuído (confirmado ao vivo) — a conta da IA entra só como
        # "segurador de lugar" pro PATCH de status funcionar de verdade.
        monkeypatch.setattr(settings, "glpi_conta_ia_id", "274-teste")
        cliente = _ClienteGLPIFake([_chamado()])
        ollama = _OllamaClienteFake(suficiente=False, mensagem="Qual sistema está afetado?")
        cargas: dict[str, int] = {}

        await processar_chamado_novo(cliente, ollama, "modelo-teste", _chamado(), cargas, True)

        assert cliente.usuarios_atribuidos == [(1, "274-teste")]

    async def test_chamado_insuficiente_com_ia_ja_atribuida_nao_reatribui(self, monkeypatch):
        # Idempotente — reavaliar (via botão individual, por exemplo) um
        # chamado que já tem a conta da IA atribuída não deveria tentar
        # atribuir de novo (GLPI rejeitaria com 400).
        monkeypatch.setattr(settings, "glpi_conta_ia_id", "274-teste")
        cliente = _ClienteGLPIFake([_chamado(tecnico_atribuido="274-teste")])
        ollama = _OllamaClienteFake(suficiente=False, mensagem="Qual sistema está afetado?")
        cargas: dict[str, int] = {}

        await processar_chamado_novo(
            cliente, ollama, "modelo-teste", _chamado(tecnico_atribuido="274-teste"), cargas, True
        )

        assert cliente.usuarios_atribuidos == []

    async def test_chamado_insuficiente_sem_conta_da_ia_configurada_pula_o_passo(self, monkeypatch):
        # Campo opcional (mesmo espírito dos outros campos de TI
        # opcionais) — sem configurar, só pula esse passo, não trava nada.
        monkeypatch.setattr(settings, "glpi_conta_ia_id", "")
        cliente = _ClienteGLPIFake([_chamado()])
        ollama = _OllamaClienteFake(suficiente=False, mensagem="Qual sistema está afetado?")
        cargas: dict[str, int] = {}

        await processar_chamado_novo(cliente, ollama, "modelo-teste", _chamado(), cargas, True)

        assert cliente.usuarios_atribuidos == []

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

    async def test_chamado_sem_categoria_suficiente_classifica_do_zero_e_vai_pra_fila(self):
        # Chamado por e-mail (sem categoria) — confirmado com quem cuida
        # do GLPI que é o padrão real desse tipo de abertura, não uma
        # falha de cadastro. Bug real visto em produção: sem classificar
        # do zero, esses chamados ficavam presos em `novo` pra sempre,
        # sendo reavaliados (gastando IA) a cada rodada do poller sem
        # nunca sair dali. Agora segue o mesmo fluxo de quem já tem
        # categoria — só que escolhendo uma do zero em vez de corrigir.
        cliente = _ClienteGLPIFake([_chamado(categoria_id=None)])
        ollama = _OllamaClienteFake(suficiente=True)
        cargas = {"tecnico1": 0}

        resultado = await processar_chamado_novo(
            cliente, ollama, "modelo-teste", _chamado(categoria_id=None), cargas, True
        )

        assert cliente.categorias_atualizadas == [(1, 999)]
        assert len(cliente.atribuicoes) == 1
        chamado_id, area, _tecnico = cliente.atribuicoes[0]
        assert chamado_id == 1
        assert area == "infra"
        assert cliente.avaliacoes == [(1, "fila_atendimento", None)]
        assert resultado.avaliacao_suficiente is True
        assert resultado.precisou_embedding is True

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
        assert resultado.embedding_indisponivel is False

    async def test_provedor_sem_embedding_marca_embedding_indisponivel_mas_nao_trava(self):
        # Ex: provedor ativo é OCI Generative AI (sem suporte a embedding) —
        # a triagem continua funcionando normal, só a correção de categoria
        # cai pro fallback (mantém a categoria atual) e fica sinalizado.
        cliente = _ClienteGLPIFake([_chamado(categoria_id=999)])
        ollama = _OllamaClienteFake(suficiente=True, levantar_no_embed=EmbeddingNaoSuportado("sem embedding"))
        cargas = {"tecnico1": 0}

        resultado = await processar_chamado_novo(
            cliente, ollama, "modelo-teste", _chamado(categoria_id=999), cargas, True
        )

        assert resultado.avaliacao_suficiente is True
        assert resultado.embedding_indisponivel is True
        assert cliente.categorias_atualizadas == []

    async def test_chamado_suficiente_sem_tecnico_na_area_levanta_sem_tecnico_na_area(self, monkeypatch):
        # Antes disso, `escolher_tecnico` estourava `ValueError` cru — sem
        # try/except em `chamado_verificar_route`, virava 500 sem mensagem
        # útil (visto ao vivo). Sobrescreve a fixture `_roster_de_tecnicos_
        # para_teste` (que sempre tem alguém em "infra") só pra este teste.
        monkeypatch.setattr("agente_oracle.tools.ti.tecnicos.listar_tecnicos_ti", lambda: [])
        cliente = _ClienteGLPIFake([_chamado(categoria_id=1)])
        ollama = _OllamaClienteFake(suficiente=True)
        cargas: dict[str, int] = {}

        with pytest.raises(SemTecnicoNaArea) as excinfo:
            await processar_chamado_novo(
                cliente, ollama, "modelo-teste", _chamado(categoria_id=1), cargas, True
            )

        assert excinfo.value.area == "infra"

    async def test_chamado_suficiente_com_ia_atribuida_desatribui_antes_do_tecnico_real(self, monkeypatch):
        # Reavaliação depois de resposta nova (`verificar_chamados_
        # aguardando_resposta`): a conta da IA estava atribuída desde a
        # 1ª avaliação insuficiente — precisa sair antes do técnico real
        # assumir de vez.
        monkeypatch.setattr(settings, "glpi_conta_ia_id", "274-teste")
        cliente = _ClienteGLPIFake([_chamado(categoria_id=1, tecnico_atribuido="274-teste")])
        ollama = _OllamaClienteFake(suficiente=True)
        cargas = {"tecnico1": 0}

        await processar_chamado_novo(
            cliente,
            ollama,
            "modelo-teste",
            _chamado(categoria_id=1, tecnico_atribuido="274-teste"),
            cargas,
            True,
        )

        assert cliente.usuarios_desatribuidos == [(1, "274-teste")]
        assert len(cliente.atribuicoes) == 1

    async def test_chamado_ja_atribuido_ao_tecnico_certo_nao_reatribui(self):
        # Confirmado contra a instância real: o GLPI rejeita (400
        # ERROR_INVALID_PARAMETER) atribuir a mesma pessoa/papel duas
        # vezes — acontece quando um chamado fica "meio processado"
        # numa rodada anterior (técnico já atribuído, mas a chamada
        # seguinte, marcar `fila_atendimento`, falhou ou foi
        # interrompida antes de terminar). Sem pular a reatribuição, o
        # chamado ficaria travado pra sempre nessa mesma falha.
        cliente = _ClienteGLPIFake([_chamado(categoria_id=999, tecnico_atribuido="7")])
        ollama = _OllamaClienteFake(suficiente=True)
        cargas = {"7": 0}

        resultado = await processar_chamado_novo(
            cliente,
            ollama,
            "modelo-teste",
            _chamado(categoria_id=999, tecnico_atribuido="7"),
            cargas,
            True,
        )

        assert cliente.atribuicoes == []
        assert cliente.avaliacoes == [(1, "fila_atendimento", None)]
        assert resultado.avaliacao_suficiente is True

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

    async def test_chamado_citando_tecnico_por_nome_prioriza_sobre_a_carga(self, monkeypatch):
        # Nome citado no chamado (ex: "abrir pro Pablo") vence a carga —
        # mesmo Pablo estando mais sobrecarregado que o outro técnico da
        # mesma área. Nunca muda a área: só reordena quem, dentro dela.
        roster = [
            {"usuario": "pablo", "nome": "Pablo Silva", "tecnico_glpi_id": "pablo", "area_ti": "infra"},
            {"usuario": "denner", "nome": "Denner Souza", "tecnico_glpi_id": "denner", "area_ti": "infra"},
        ]
        monkeypatch.setattr("agente_oracle.tools.ti.tecnicos.listar_tecnicos_ti", lambda: roster)
        chamado = _chamado(
            categoria_id=999,
            titulo="Abrir chamado pro Pablo",
            descricao=_DESCRICAO_PADRAO_TESTE,
        )
        cliente = _ClienteGLPIFake([chamado])
        ollama = _OllamaClienteFake(suficiente=True)
        cargas = {"pablo": 5, "denner": 0}

        await processar_chamado_novo(cliente, ollama, "modelo-teste", chamado, cargas, True)

        _chamado_id, _area, tecnico = cliente.atribuicoes[0]
        assert tecnico == "pablo"

    async def test_chamado_sem_nome_citado_continua_escolhendo_por_carga(self, monkeypatch):
        roster = [
            {"usuario": "pablo", "nome": "Pablo Silva", "tecnico_glpi_id": "pablo", "area_ti": "infra"},
            {"usuario": "denner", "nome": "Denner Souza", "tecnico_glpi_id": "denner", "area_ti": "infra"},
        ]
        monkeypatch.setattr("agente_oracle.tools.ti.tecnicos.listar_tecnicos_ti", lambda: roster)
        chamado = _chamado(categoria_id=999)
        cliente = _ClienteGLPIFake([chamado])
        ollama = _OllamaClienteFake(suficiente=True)
        cargas = {"pablo": 5, "denner": 0}

        await processar_chamado_novo(cliente, ollama, "modelo-teste", chamado, cargas, True)

        _chamado_id, _area, tecnico = cliente.atribuicoes[0]
        assert tecnico == "denner"

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

    async def test_insuficiente_apos_bater_o_limite_de_rodadas_escala_pro_tecnico(self):
        # Bug real visto em produção (#3262): sem essa distinção, a IA
        # manda a mesma pergunta genérica de novo a cada reavaliação.
        # Agora o corte é `_LIMITE_RODADAS_ESCLARECIMENTO` (3) respostas
        # do solicitante ainda insuficientes — bate isso, atribui um
        # técnico humano em vez de continuar perguntando. Atribuir alguém
        # muda o status sozinho pra "Em atendimento" (confirmado ao vivo)
        # — por isso o escalonamento também chama `atualizar_avaliacao`
        # com `fila_atendimento`, deixando isso explícito.
        cliente = _ClienteGLPIFake([_chamado(categoria_id=999)])
        cliente.followups_por_chamado[1] = _followups_ciclo(3)
        ollama = _OllamaClienteFake(suficiente=False, mensagem="Qual sistema está afetado?")
        cargas = {"7": 0}

        resultado = await processar_chamado_novo(
            cliente, ollama, "modelo-teste", _chamado(categoria_id=999), cargas, True
        )

        assert len(cliente.avaliacoes) == 1
        chamado_id, status, mensagem = cliente.avaliacoes[0]
        assert (chamado_id, status) == (1, "fila_atendimento")
        assert mensagem is not None and "Triagem automática" in mensagem  # resumo pro técnico
        assert len(cliente.atribuicoes) == 1
        chamado_id, area, _tecnico = cliente.atribuicoes[0]
        assert chamado_id == 1
        assert area == "infra"
        assert resultado.avaliacao_suficiente is False

    async def test_insuficiente_com_menos_rodadas_que_o_limite_continua_perguntando(self):
        # Menos de 3 respostas do solicitante ainda: mais uma rodada de
        # esclarecimento (aguardando_usuario), não escala ainda.
        cliente = _ClienteGLPIFake([_chamado(categoria_id=999)])
        cliente.followups_por_chamado[1] = _followups_ciclo(2)
        ollama = _OllamaClienteFake(suficiente=False, mensagem="E qual a frequência?")
        cargas = {"7": 0}

        resultado = await processar_chamado_novo(
            cliente, ollama, "modelo-teste", _chamado(categoria_id=999), cargas, True
        )

        assert cliente.avaliacoes == [(1, "aguardando_usuario", "E qual a frequência?")]
        assert cliente.atribuicoes == []
        assert resultado.avaliacao_suficiente is False

    async def test_regra_disparando_numa_rodada_alem_da_primeira_escala_em_vez_de_repetir(self):
        # `_avaliar_por_regra` sempre devolve o MESMO texto fixo — deixar
        # isso repetir numa rodada além da 1ª seria o próprio bug #3262.
        # `usar_ia=False` força o caminho da regra mesmo com 1 resposta já
        # registrada (rodada > 0) — descrição vazia o bastante pra, mesmo
        # somada com a resposta do followup, continuar batendo a regra
        # (_MINIMO_PALAVRAS_DESCRICAO = 5).
        chamado_curto = _chamado(categoria_id=999, descricao="")
        cliente = _ClienteGLPIFake([chamado_curto])
        cliente.followups_por_chamado[1] = _followups_ciclo(1)
        ollama = _OllamaClienteFake(suficiente=False, mensagem="não deveria ser usada")
        cargas = {"7": 0}

        resultado = await processar_chamado_novo(cliente, ollama, "modelo-teste", chamado_curto, cargas, False)

        assert len(cliente.avaliacoes) == 1
        assert cliente.avaliacoes[0][1] == "fila_atendimento"
        assert len(cliente.atribuicoes) == 1
        assert resultado.avaliacao_suficiente is False

    async def test_ia_repetindo_pergunta_parecida_escala_mesmo_sem_bater_o_limite(self):
        # Rede de segurança pro caso real do chamado #3340: mesmo vindo da
        # IA de verdade (não da regra) e ainda dentro do limite de
        # rodadas, uma pergunta parecida demais com uma que a própria IA
        # já fez nesta conversa escala em vez de repetir.
        cliente = _ClienteGLPIFake([_chamado(categoria_id=999)])
        cliente.followups_por_chamado[1] = _followups_ciclo(1)  # 1 rodada, bem abaixo do limite (3)
        ollama = _OllamaClienteFake(suficiente=False, mensagem="Pergunta 1 da IA")  # igual à pergunta anterior
        cargas = {"7": 0}

        resultado = await processar_chamado_novo(
            cliente, ollama, "modelo-teste", _chamado(categoria_id=999), cargas, True
        )

        assert len(cliente.avaliacoes) == 1
        assert cliente.avaliacoes[0][1] == "fila_atendimento"
        assert len(cliente.atribuicoes) == 1
        assert resultado.avaliacao_suficiente is False

    async def test_escalonamento_desatribui_a_conta_da_ia_se_estiver_atribuida(self, monkeypatch):
        monkeypatch.setattr(settings, "glpi_conta_ia_id", "274-teste")
        cliente = _ClienteGLPIFake([_chamado(categoria_id=999, tecnico_atribuido="274-teste")])
        cliente.followups_por_chamado[1] = _followups_ciclo(3)
        ollama = _OllamaClienteFake(suficiente=False, mensagem="Qual sistema está afetado?")
        cargas = {"7": 0}

        await processar_chamado_novo(
            cliente,
            ollama,
            "modelo-teste",
            _chamado(categoria_id=999, tecnico_atribuido="274-teste"),
            cargas,
            True,
        )

        assert cliente.usuarios_desatribuidos == [(1, "274-teste")]
        assert len(cliente.atribuicoes) == 1

    async def test_insuficiente_apos_limite_sem_categoria_usa_area_padrao(self):
        # Chamado aberto por e-mail (sem categoria) que segue insuficiente
        # depois de esgotar as rodadas ainda precisa de alguém pra
        # escalar — cai na área padrão em vez de travar por falta de
        # categoria.
        cliente = _ClienteGLPIFake([_chamado(categoria_id=None)])
        cliente.followups_por_chamado[1] = _followups_ciclo(3)
        ollama = _OllamaClienteFake(suficiente=False, mensagem="Qual sistema está afetado?")
        cargas: dict[str, int] = {}

        await processar_chamado_novo(cliente, ollama, "modelo-teste", _chamado(categoria_id=None), cargas, True)

        assert len(cliente.atribuicoes) == 1
        _chamado_id, area, _tecnico = cliente.atribuicoes[0]
        assert area == "sistemas"


class TestVerificarChamadosPendentes:
    async def test_reprocessa_so_novo_ignora_aguardando_usuario(self, monkeypatch):
        # Reavaliar `aguardando_usuario` de novo a cada rodada (a cada 5
        # min, via poller) gastaria IA à toa sem que o solicitante tenha
        # respondido nada — só `novo` é reprocessado (ver docstring de
        # `verificar_chamados_pendentes`). `aguardando_usuario` continua
        # saindo no retorno (é o que alimenta a tela), só não é escrito.
        chamado_novo = _chamado(id_=1, categoria_id=999)
        chamado_pendente = replace(_chamado(id_=2, categoria_id=999), status="aguardando_usuario")
        cliente = _ClienteGLPIFake([chamado_novo, chamado_pendente])
        monkeypatch.setattr(chamados_module, "_cliente", cliente)
        monkeypatch.setattr(
            chamados_module, "criar_cliente_protegido", lambda *_args, **_kwargs: _OllamaClienteFake(suficiente=True)
        )

        resultado = await verificar_chamados_pendentes(usar_ia=True)

        assert cliente.avaliacoes == [(1, "fila_atendimento", None)]
        assert {chamado_id for chamado_id, *_ in cliente.atribuicoes} == {1}
        assert {chamado.id for chamado in resultado} == {1, 2}

    async def test_falha_num_chamado_nao_bloqueia_o_resto_do_lote(self, monkeypatch):
        # Reproduz o bug real do chamado #2660: um chamado que quebra ao
        # processar (ex: GLPI rejeitando reatribuição duplicada) não pode
        # travar todo mundo que vem depois dele na lista — sem isolar por
        # chamado, essa exceção interrompia o `for` inteiro, e nenhum
        # chamado seguinte era processado, nem naquela rodada nem em
        # nenhuma das próximas.
        chamado_com_erro = _chamado(id_=1, categoria_id=999)
        chamado_ok = _chamado(id_=2, categoria_id=999)
        cliente = _ClienteGLPIFake([chamado_com_erro, chamado_ok])

        atribuir_original = cliente.atribuir

        async def _atribuir_falha_no_primeiro(chamado_id, area, tecnico_identificador):
            if chamado_id == 1:
                raise RuntimeError("400 simulado do GLPI")
            await atribuir_original(chamado_id, area, tecnico_identificador)

        cliente.atribuir = _atribuir_falha_no_primeiro
        monkeypatch.setattr(chamados_module, "_cliente", cliente)
        monkeypatch.setattr(
            chamados_module, "criar_cliente_protegido", lambda *_args, **_kwargs: _OllamaClienteFake(suficiente=True)
        )

        resultado = await verificar_chamados_pendentes(usar_ia=True)

        assert cliente.avaliacoes == [(2, "fila_atendimento", None)]
        assert {chamado_id for chamado_id, *_ in cliente.atribuicoes} == {2}
        assert {chamado.id for chamado in resultado} == {1, 2}

    async def test_so_processa_os_chamados_que_entram_na_amostra(self, monkeypatch):
        cliente = _ClienteGLPIFake([_chamado(id_=1, categoria_id=999), _chamado(id_=2, categoria_id=999)])
        monkeypatch.setattr(chamados_module, "_cliente", cliente)
        monkeypatch.setattr(chamados_module.uso_ia_chamados, "ultima_avaliacao", lambda _id: None)
        monkeypatch.setattr(
            chamados_module.amostragem_chamados, "deve_analisar", lambda id_, _criado_em=None: id_ == 1
        )
        monkeypatch.setattr(
            chamados_module, "criar_cliente_protegido", lambda *_args, **_kwargs: _OllamaClienteFake(suficiente=True)
        )

        resultado = await verificar_chamados_pendentes(usar_ia=True)

        assert cliente.avaliacoes == [(1, "fila_atendimento", None)]
        # O chamado fora da amostra continua na listagem devolvida — quem
        # esconde ele da tela é `_chamados_da_tela`, não este loop.
        assert {chamado.id for chamado in resultado} == {1, 2}

    async def test_chamado_ja_avaliado_antes_ignora_a_amostragem(self, monkeypatch):
        # Ficou "meio processado" numa rodada anterior: já está no ciclo,
        # a amostra não pode largar ele no meio do caminho.
        cliente = _ClienteGLPIFake([_chamado(id_=1, categoria_id=999)])
        registro_anterior = uso_ia_chamados.RegistroUsoIa(
            avaliacao_suficiente=True, criado_em=datetime(2026, 1, 1, tzinfo=UTC)
        )
        monkeypatch.setattr(chamados_module, "_cliente", cliente)
        monkeypatch.setattr(
            chamados_module.uso_ia_chamados, "ultima_avaliacao", lambda _id: registro_anterior
        )

        def _amostragem_proibida(_id, _criado_em=None):
            raise AssertionError("chamado já avaliado não deveria passar pela amostragem")

        monkeypatch.setattr(chamados_module.amostragem_chamados, "deve_analisar", _amostragem_proibida)
        monkeypatch.setattr(
            chamados_module, "criar_cliente_protegido", lambda *_args, **_kwargs: _OllamaClienteFake(suficiente=True)
        )

        await verificar_chamados_pendentes(usar_ia=True)

        assert cliente.avaliacoes == [(1, "fila_atendimento", None)]

    async def test_falha_no_banco_da_amostragem_nao_processa_nenhum_chamado(self, monkeypatch):
        cliente = _ClienteGLPIFake([_chamado(id_=1, categoria_id=999)])
        monkeypatch.setattr(chamados_module, "_cliente", cliente)
        monkeypatch.setattr(chamados_module.uso_ia_chamados, "ultima_avaliacao", lambda _id: None)

        def _banco_fora(_id, _criado_em=None):
            raise psycopg.OperationalError("Postgres fora do ar")

        monkeypatch.setattr(chamados_module.amostragem_chamados, "deve_analisar", _banco_fora)
        monkeypatch.setattr(
            chamados_module, "criar_cliente_protegido", lambda *_args, **_kwargs: _OllamaClienteFake(suficiente=True)
        )

        await verificar_chamados_pendentes(usar_ia=True)

        assert cliente.avaliacoes == []
        assert cliente.atribuicoes == []


class TestClienteProtegidoDeVerdade:
    """Diferente do resto da suíte (que troca `criar_cliente_protegido` por
    um fake direto): aqui o `ClienteOllamaProtegido` de verdade roda —
    confirma que o texto que chegaria no Ollama já sai saneado, sem editar
    nenhuma linha de `agent/ti/qualidade_chamado.py`/`roteamento_chamado.py`.
    Só o `AsyncClient` por baixo e a auditoria (Postgres) são fake, pra
    continuar sem rede/banco real num teste unitário."""

    async def test_descricao_com_cpf_chega_mascarada_no_ollama(self, monkeypatch):
        from agente_oracle.tools.ia import auditoria_externa, configuracoes_provedor
        from agente_oracle.tools.ia import cliente_protegido as cliente_protegido_module

        cliente_ollama_fake = _OllamaClienteFake(suficiente=True)
        monkeypatch.setattr(cliente_protegido_module, "AsyncClient", lambda **_kwargs: cliente_ollama_fake)
        monkeypatch.setattr(auditoria_externa, "registrar", lambda *_args: None)
        monkeypatch.setattr(auditoria_externa, "contagem_hoje", lambda _dominio: 0)
        # Isola do banco real: este teste quer especificamente o caminho
        # `ollama.AsyncClient` (nenhum provedor cadastrado ativo) — sem
        # isso, ele passa a depender do que estiver ativado no Postgres de
        # dev no momento (ex: um provedor OpenAI-compatível cadastrado
        # manualmente pra teste), que usaria `ClienteOpenAICompativel` em
        # vez do `AsyncClient` mockado aqui.
        monkeypatch.setattr(configuracoes_provedor, "provedor_llm_ativo_id", lambda: None)

        chamado = _chamado(
            categoria_id=999, descricao=_DESCRICAO_PADRAO_TESTE + " Meu CPF é 123.456.789-00."
        )
        cliente = _ClienteGLPIFake([chamado])
        monkeypatch.setattr(chamados_module, "_cliente", cliente)

        await verificar_chamados_pendentes(usar_ia=True)

        conteudo_enviado = cliente_ollama_fake.chamadas_chat[0]["messages"][1]["content"]
        assert "123.456.789-00" not in conteudo_enviado
        assert "[CPF]" in conteudo_enviado


class TestChamadoEntraNaAmostra:
    def test_devolve_a_decisao_da_amostragem(self, monkeypatch):
        monkeypatch.setattr(
            chamados_module.amostragem_chamados, "deve_analisar", lambda id_, _criado_em=None: id_ == 7
        )

        assert chamado_entra_na_amostra(7) is True
        assert chamado_entra_na_amostra(8) is False

    def test_falha_do_banco_falha_pro_lado_fechado(self, monkeypatch):
        # Cair pro lado aberto analisaria todo mundo justamente quando não
        # dá pra saber se o chamado estava fora da amostra.
        def _banco_fora(_id, _criado_em=None):
            raise psycopg.OperationalError("Postgres fora do ar")

        monkeypatch.setattr(chamados_module.amostragem_chamados, "deve_analisar", _banco_fora)

        assert chamado_entra_na_amostra(7) is False


class TestChamadosDaTela:
    def test_esconde_chamado_fora_da_amostra(self):
        chamados = [_chamado(id_=1), _chamado(id_=2), _chamado(id_=3)]

        resultado = _chamados_da_tela(chamados, fora_da_amostra={2})

        assert [chamado["id"] for chamado in resultado] == [1, 3]

    def test_continua_escondendo_fila_de_atendimento(self):
        na_fila = replace(_chamado(id_=1), status="fila_atendimento")

        assert _chamados_da_tela([na_fila, _chamado(id_=2)], fora_da_amostra=set()) == [
            chamados_module._chamado_para_json(_chamado(id_=2))
        ]


class TestVerificarChamadosAguardandoResposta:
    async def test_reavalia_quando_tem_resposta_nova_do_solicitante(self, monkeypatch):
        chamado_pendente = replace(_chamado(id_=1, categoria_id=999), status="aguardando_usuario")
        cliente = _ClienteGLPIFake([chamado_pendente])
        registro_anterior = uso_ia_chamados.RegistroUsoIa(
            avaliacao_suficiente=False, criado_em=datetime(2026, 1, 1, tzinfo=UTC)
        )
        cliente.followups_por_chamado[1] = [
            Followup(
                autor_id=999,
                autor_nome="solicitante.teste",
                conteudo="Ah, é o sistema X que trava.",
                criado_em=datetime(2026, 1, 2, tzinfo=UTC),
            )
        ]
        monkeypatch.setattr(chamados_module, "_cliente", cliente)
        monkeypatch.setattr(
            chamados_module.uso_ia_chamados, "ultima_avaliacao", lambda _id: registro_anterior
        )
        monkeypatch.setattr(
            chamados_module, "criar_cliente_protegido", lambda *_args, **_kwargs: _OllamaClienteFake(suficiente=True)
        )

        await verificar_chamados_aguardando_resposta(usar_ia=True)

        assert cliente.avaliacoes == [(1, "fila_atendimento", None)]
        assert len(cliente.atribuicoes) == 1

    async def test_nao_reavalia_sem_resposta_nova(self, monkeypatch):
        # Followup existe, mas é da própria conta de serviço (a pergunta
        # que a IA já fez) — não conta como resposta nova.
        chamado_pendente = replace(_chamado(id_=1, categoria_id=999), status="aguardando_usuario")
        cliente = _ClienteGLPIFake([chamado_pendente])
        registro_anterior = uso_ia_chamados.RegistroUsoIa(
            avaliacao_suficiente=False, criado_em=datetime(2026, 1, 1, tzinfo=UTC)
        )
        cliente.followups_por_chamado[1] = [
            Followup(
                autor_id=274,
                autor_nome=settings.glpi_username,
                conteudo="Qual sistema está afetado?",
                criado_em=datetime(2026, 1, 2, tzinfo=UTC),
            )
        ]
        monkeypatch.setattr(chamados_module, "_cliente", cliente)
        monkeypatch.setattr(
            chamados_module.uso_ia_chamados, "ultima_avaliacao", lambda _id: registro_anterior
        )
        monkeypatch.setattr(
            chamados_module, "criar_cliente_protegido", lambda *_args, **_kwargs: _OllamaClienteFake(suficiente=True)
        )

        await verificar_chamados_aguardando_resposta(usar_ia=True)

        assert cliente.avaliacoes == []
        assert cliente.atribuicoes == []

    async def test_pula_chamado_sem_registro_anterior(self, monkeypatch):
        # Não deveria acontecer na prática (`aguardando_usuario` só existe
        # depois de pelo menos 1 avaliação), mas não deveria quebrar nem
        # assumir nada se acontecer.
        chamado_pendente = replace(_chamado(id_=1, categoria_id=999), status="aguardando_usuario")
        cliente = _ClienteGLPIFake([chamado_pendente])
        monkeypatch.setattr(chamados_module, "_cliente", cliente)
        monkeypatch.setattr(chamados_module.uso_ia_chamados, "ultima_avaliacao", lambda _id: None)
        monkeypatch.setattr(
            chamados_module, "criar_cliente_protegido", lambda *_args, **_kwargs: _OllamaClienteFake(suficiente=True)
        )

        await verificar_chamados_aguardando_resposta(usar_ia=True)

        assert cliente.avaliacoes == []
        assert cliente.atribuicoes == []


class TestTextoParaIa:
    def test_tira_tags_e_extrai_texto(self):
        html = "<p>Computador <strong>não liga</strong> desde ontem.</p>"
        assert _texto_para_ia(html) == "Computador não liga desde ontem."

    def test_tira_bloco_de_estilo_inteiro(self):
        # `<style>` traz regra CSS, não conteúdo — não devia sobrar nem
        # como texto solto.
        html = "<style>.header { color: red; font-size: 12px; }</style><p>Texto real.</p>"
        assert _texto_para_ia(html) == "Texto real."

    def test_email_com_boilerplate_confirmado_ao_vivo(self):
        # Trecho reduzido do e-mail real que causou a inconsistência
        # (ticket #3272) — confirma que o conteúdo de verdade sobrevive
        # à limpeza, mesmo com tabela/estilo em volta.
        html = (
            '<table style="background-color: #efefef;" width="100%">'
            "<tbody><tr><td>"
            "<p>Solicitação: Paulo Henrique de Almeida wants to access "
            "'Tabela_auxiliar_barter.xlsx'</p>"
            "</td></tr></tbody></table>"
        )
        texto = _texto_para_ia(html)
        assert "Solicitação: Paulo Henrique de Almeida wants to access" in texto
        assert "<table" not in texto
        assert "background-color" not in texto

    def test_texto_sem_html_passa_direto(self):
        assert _texto_para_ia("Só texto simples, sem tag nenhuma.") == "Só texto simples, sem tag nenhuma."

    def test_string_vazia_devolve_vazia(self):
        assert _texto_para_ia("") == ""


class TestProcessarChamadoNovoLimpaHtml:
    async def test_manda_texto_limpo_pro_ollama_nao_html_cru(self):
        # A mesma checagem, só que na ponta a ponta: `processar_chamado_novo`
        # não deveria vazar HTML pro prompt da IA.
        descricao_html = (
            "<style>.x{color:red}</style><p>Sistema <b>lento</b> desde ontem de manhã, no financeiro, "
            "trava sempre que tento gerar o relatório de vendas do mês passado.</p>"
        )
        chamado = _chamado(descricao=descricao_html, categoria_id=999)
        cliente = _ClienteGLPIFake([chamado])
        ollama = _OllamaClienteFake(suficiente=True)
        cargas = {"tecnico1": 0}

        await processar_chamado_novo(cliente, ollama, "modelo-teste", chamado, cargas, True)

        assert len(ollama.chamadas_chat) == 1
        mensagem_usuario = ollama.chamadas_chat[0]["messages"][1]["content"]
        assert "<style>" not in mensagem_usuario
        assert "<p>" not in mensagem_usuario
        assert "Sistema lento desde ontem de manhã, no financeiro" in mensagem_usuario


class TestSaudePorArea:
    def test_conta_tecnico_por_area(self):
        tecnicos = (
            Tecnico(nome="Denner", identificador="1", area="infra", usuario="denner"),
            Tecnico(nome="Carlos", identificador="2", area="infra", usuario="carlos"),
            Tecnico(nome="Suellen", identificador="3", area="sistemas", usuario="suellen"),
        )

        resultado = _saude_por_area(tecnicos, cargas={})

        assert resultado == [
            {
                "area": "infra",
                "rotulo": "Infraestrutura",
                "quantidade": 2,
                "tecnicos": [
                    {"nome": "Denner", "usuario": "denner", "chamados_abertos": 0},
                    {"nome": "Carlos", "usuario": "carlos", "chamados_abertos": 0},
                ],
            },
            {
                "area": "sistemas",
                "rotulo": "Sistemas",
                "quantidade": 1,
                "tecnicos": [{"nome": "Suellen", "usuario": "suellen", "chamados_abertos": 0}],
            },
            {"area": "processos", "rotulo": "Processos", "quantidade": 0, "tecnicos": []},
        ]

    def test_roster_vazio_devolve_todas_as_areas_zeradas(self):
        # O bug real que motivou este painel: `listar_tecnicos_ti()` sem
        # nenhum usuário com `tecnico_glpi_id` preenchido devolve roster
        # vazio, e `escolher_tecnico` estoura `ValueError` (min() de lista
        # vazia) na primeira vez que precisa atribuir um chamado — este
        # painel existe pra pegar isso ANTES, mostrando as 3 áreas zeradas.
        resultado = _saude_por_area((), cargas={})

        assert [item["quantidade"] for item in resultado] == [0, 0, 0]

    def test_carga_vem_do_dict_de_carga_atual_do_glpi(self):
        tecnicos = (Tecnico(nome="Denner", identificador="1", area="infra", usuario="denner"),)

        resultado = _saude_por_area(tecnicos, cargas={"1": 9})

        assert resultado[0]["tecnicos"] == [{"nome": "Denner", "usuario": "denner", "chamados_abertos": 9}]

    def test_tecnico_sem_entrada_em_cargas_conta_zero(self):
        # `carga_atual_por_tecnico` só lista quem tem chamado em
        # `fila_atendimento` no momento — técnico sem nenhum não aparece no
        # dict, e isso não pode virar KeyError aqui.
        tecnicos = (Tecnico(nome="Denner", identificador="1", area="infra", usuario="denner"),)

        resultado = _saude_por_area(tecnicos, cargas={})

        assert resultado[0]["tecnicos"] == [{"nome": "Denner", "usuario": "denner", "chamados_abertos": 0}]
