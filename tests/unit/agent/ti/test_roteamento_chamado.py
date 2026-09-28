import pytest

from agente_oracle.agent.ti import roteamento_chamado as mod
from agente_oracle.tools.ti.categorias import CategoriaGlpi

_CATEGORIAS_FAKE = (
    CategoriaGlpi(1, "cat infra", "infra"),
    CategoriaGlpi(2, "cat sistemas", "sistemas"),
    CategoriaGlpi(3, "cat processos", "processos"),
)
_AREA_POR_ID_FAKE = {categoria.id: categoria.area for categoria in _CATEGORIAS_FAKE}

# Vetores ortogonais por categoria — deixa a similaridade de cosseno
# inequívoca sobre qual categoria "vence" pra cada texto de chamado.
_VETOR_POR_NOME = {
    "cat infra": [1.0, 0.0, 0.0],
    "cat sistemas": [0.0, 1.0, 0.0],
    "cat processos": [0.0, 0.0, 1.0],
}


@pytest.fixture(autouse=True)
def _categorias_fake(monkeypatch):
    monkeypatch.setattr(mod.categorias, "CATEGORIAS_ATRIBUIVEIS", _CATEGORIAS_FAKE)
    monkeypatch.setattr(mod.categorias, "AREA_POR_CATEGORIA_ID", _AREA_POR_ID_FAKE)
    monkeypatch.setattr(mod, "_cache_embeddings_categorias", None)


class _EmbedRespostaFake:
    def __init__(self, embedding: list[float]):
        self.embeddings = [embedding]


class _OllamaEmbedFake:
    def __init__(self, resolver=None, levantar: Exception | None = None):
        self._resolver = resolver or (lambda texto: _VETOR_POR_NOME.get(texto, [1.0, 0.0, 0.0]))
        self._levantar = levantar
        self.chamadas = 0

    async def embed(self, **kwargs):
        self.chamadas += 1
        if self._levantar:
            raise self._levantar
        return _EmbedRespostaFake(self._resolver(kwargs.get("input", "")))


class TestClassificarCategoria:
    async def test_usar_ia_false_nunca_chama_embed_e_mantem_area_atual(self):
        cliente = _OllamaEmbedFake()
        resultado = await mod.classificar_categoria(
            cliente, "modelo-embed", "titulo", "descricao", 1, usar_ia=False
        )
        assert resultado.area == "infra"
        assert resultado.categoria_id is None
        assert resultado.precisou_embedding is False
        assert cliente.chamadas == 0

    async def test_usar_ia_false_sem_categoria_atual_cai_pra_area_padrao(self):
        cliente = _OllamaEmbedFake()
        resultado = await mod.classificar_categoria(
            cliente, "modelo-embed", "titulo", "descricao", None, usar_ia=False
        )
        assert resultado.area == mod._AREA_PADRAO
        assert resultado.categoria_id is None
        assert cliente.chamadas == 0

    async def test_categoria_atual_ja_correta_nao_corrige(self):
        def resolver(texto: str) -> list[float]:
            if texto in _VETOR_POR_NOME:
                return _VETOR_POR_NOME[texto]
            return [1.0, 0.0, 0.0]  # texto do chamado — mais parecido com "cat infra"

        cliente = _OllamaEmbedFake(resolver=resolver)
        resultado = await mod.classificar_categoria(
            cliente, "modelo-embed", "titulo", "descricao", 1, usar_ia=True
        )
        assert resultado.area == "infra"
        assert resultado.categoria_id is None
        assert resultado.precisou_embedding is True

    async def test_categoria_atual_errada_corrige_para_categoria_real(self):
        def resolver(texto: str) -> list[float]:
            if texto in _VETOR_POR_NOME:
                return _VETOR_POR_NOME[texto]
            return [0.0, 1.0, 0.0]  # texto do chamado — mais parecido com "cat sistemas"

        cliente = _OllamaEmbedFake(resolver=resolver)
        resultado = await mod.classificar_categoria(
            cliente, "modelo-embed", "titulo", "descricao", 1, usar_ia=True
        )
        assert resultado.area == "sistemas"
        assert resultado.categoria_id == 2
        assert resultado.precisou_embedding is True

    async def test_categoria_atual_errada_mas_mesma_area_ainda_assim_corrige(self, monkeypatch):
        # Regressão de bug real achado pelo usuário (2026-09-28): usuário
        # escolheu manualmente uma categoria errada que por coincidência já
        # está na área certa (ex: marcou "Sharepoint" — infra — pra um
        # chamado de impressora — também infra). A comparação antiga era
        # só `escolhida.area == area_atual`, então esse caso nunca era
        # corrigido — a área batia, "parecia" já estar certo. Usa um
        # catálogo local (2 categorias, mesma área) só pra este teste, em
        # vez do `_categorias_fake` compartilhado (1 categoria por área,
        # não dava pra testar esse cenário).
        categorias_locais = (
            CategoriaGlpi(1, "cat infra A", "infra"),
            CategoriaGlpi(4, "cat infra B", "infra"),
        )
        monkeypatch.setattr(mod.categorias, "CATEGORIAS_ATRIBUIVEIS", categorias_locais)
        monkeypatch.setattr(mod.categorias, "AREA_POR_CATEGORIA_ID", {c.id: c.area for c in categorias_locais})
        monkeypatch.setattr(mod, "_cache_embeddings_categorias", None)

        def resolver(texto: str) -> list[float]:
            vetores = {"cat infra A": [1.0, 0.0], "cat infra B": [0.0, 1.0]}
            return vetores.get(texto, [0.0, 1.0])  # texto do chamado — mais parecido com "cat infra B"

        cliente = _OllamaEmbedFake(resolver=resolver)
        # Usuário escolheu a categoria 1 ("cat infra A") — errada.
        resultado = await mod.classificar_categoria(
            cliente, "modelo-embed", "titulo", "descricao", 1, usar_ia=True
        )

        assert resultado.area == "infra"  # área já estava certa
        assert resultado.categoria_id == 4  # mas corrige pra categoria B mesmo assim

    async def test_sem_categoria_atual_e_ia_escolhe_uma_sempre_corrige(self):
        def resolver(texto: str) -> list[float]:
            if texto in _VETOR_POR_NOME:
                return _VETOR_POR_NOME[texto]
            return [0.0, 0.0, 1.0]  # texto do chamado — mais parecido com "cat processos"

        cliente = _OllamaEmbedFake(resolver=resolver)
        resultado = await mod.classificar_categoria(
            cliente, "modelo-embed", "titulo", "descricao", None, usar_ia=True
        )
        assert resultado.area == "processos"
        assert resultado.categoria_id == 3

    async def test_falha_no_ollama_cai_pra_area_atual_sem_corrigir(self):
        cliente = _OllamaEmbedFake(levantar=ConnectionError("Ollama fora do ar"))
        resultado = await mod.classificar_categoria(
            cliente, "modelo-embed", "titulo", "descricao", 2, usar_ia=True
        )
        assert resultado.area == "sistemas"
        assert resultado.categoria_id is None
        assert resultado.precisou_embedding is True

    async def test_falha_no_ollama_sem_categoria_atual_cai_pra_area_padrao(self):
        cliente = _OllamaEmbedFake(levantar=ConnectionError("Ollama fora do ar"))
        resultado = await mod.classificar_categoria(
            cliente, "modelo-embed", "titulo", "descricao", None, usar_ia=True
        )
        assert resultado.area == mod._AREA_PADRAO
        assert resultado.categoria_id is None

    async def test_falha_de_rede_nao_marca_embedding_indisponivel(self):
        # Falha genérica (Ollama fora do ar, timeout etc.) cai no mesmo
        # fallback, mas não é "provedor sem suporte a embedding" — não pode
        # confundir os dois casos, senão o aviso pro usuário mente.
        cliente = _OllamaEmbedFake(levantar=ConnectionError("Ollama fora do ar"))
        resultado = await mod.classificar_categoria(
            cliente, "modelo-embed", "titulo", "descricao", 2, usar_ia=True
        )
        assert resultado.embedding_indisponivel is False

    async def test_provedor_sem_suporte_a_embedding_marca_embedding_indisponivel(self):
        cliente = _OllamaEmbedFake(levantar=mod.EmbeddingNaoSuportado("sem embedding nesse provedor"))
        resultado = await mod.classificar_categoria(
            cliente, "modelo-embed", "titulo", "descricao", 2, usar_ia=True
        )
        assert resultado.area == "sistemas"
        assert resultado.embedding_indisponivel is True

    async def test_categoria_corrigida_com_sucesso_nao_marca_embedding_indisponivel(self):
        cliente = _OllamaEmbedFake()
        resultado = await mod.classificar_categoria(
            cliente, "modelo-embed", "titulo", "descricao", None, usar_ia=True
        )
        assert resultado.embedding_indisponivel is False

    async def test_cache_de_embeddings_das_categorias_e_reaproveitado(self):
        cliente = _OllamaEmbedFake()

        await mod.classificar_categoria(cliente, "modelo-embed", "titulo1", "descricao1", 1, usar_ia=True)
        chamadas_apos_primeira = cliente.chamadas
        assert chamadas_apos_primeira == len(_CATEGORIAS_FAKE) + 1  # 3 categorias + 1 do chamado

        await mod.classificar_categoria(cliente, "modelo-embed", "titulo2", "descricao2", 1, usar_ia=True)
        # Segunda chamada só gera 1 embedding novo (o do chamado) — as
        # categorias já estão cacheadas.
        assert cliente.chamadas == chamadas_apos_primeira + 1
