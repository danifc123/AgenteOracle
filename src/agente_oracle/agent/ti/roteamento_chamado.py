"""Validação/correção de categoria do chamado contra as ~211 categorias
reais do GLPI (`tools/ti/categorias.py`) — nunca inventa classificação
própria. A IA compara o conteúdo do chamado com o catálogo real e decide:
a categoria que o usuário já escolheu bate com o conteúdo, ou existe uma
categoria real mais adequada? A área (`processos`/`sistemas`/`infra`) sai
de graça da categoria escolhida, porque cada uma já vem com o grupo GLPI
dono dela (`CategoriaGlpi.area`).

Nunca falha, nunca trava um chamado real — falha do Ollama (ou
`usar_ia=False`, a flag do time de TI) cai pra área já resolvida da
categoria atual, sem tentar corrigir nada; sem categoria atual nenhuma
(nem isso), cai pra `_AREA_PADRAO`.

`_cache_embeddings_categorias` existe porque comparar contra 211
categorias a cada chamado significaria 211 chamadas de embedding por
chamado — em vez disso, calcula uma vez só (na primeira classificação do
processo) e reaproveita depois; só 1 embedding novo (o do próprio
chamado) é gerado a cada chamada real."""

import math
from dataclasses import dataclass

from ollama import AsyncClient

from agente_oracle.tools.ia.cliente_openai_compativel import EmbeddingNaoSuportado
from agente_oracle.tools.ti import categorias
from agente_oracle.tools.ti.categorias import CategoriaGlpi
from agente_oracle.tools.ti.glpi import AreaChamado

_AREA_PADRAO: AreaChamado = "processos"

_cache_embeddings_categorias: dict[int, list[float]] | None = None


@dataclass(frozen=True)
class ResultadoClassificacao:
    area: AreaChamado
    # ID da categoria corrigida — só preenchido quando a categoria atual
    # estava errada (precisa de um `PATCH` de verdade no GLPI). `None`
    # quando a atual já estava certa, ou quando não deu pra avaliar
    # (usar_ia=False, falha do Ollama).
    categoria_id: int | None
    precisou_embedding: bool
    # `True` só quando a falha foi especificamente o provedor de IA ativo
    # não suportar embedding (`EmbeddingNaoSuportado` — ex: OCI Generative
    # AI). Outra falha (rede, provedor fora do ar) cai no mesmo fallback,
    # mas deixa isso `False` — quem chama usa pra avisar o usuário direito
    # em vez de confundir os dois casos (ver `server/ti/chamados.py`).
    embedding_indisponivel: bool = False


async def classificar_categoria(
    ollama_client: AsyncClient,
    modelo_embedding: str,
    titulo: str,
    descricao: str,
    categoria_atual_id: int | None,
    usar_ia: bool,
) -> ResultadoClassificacao:
    """`usar_ia=False` nunca chama o Ollama — mantém a categoria atual e
    usa a área que já dava pra resolver dela (ou `_AREA_PADRAO` se a
    categoria atual for desconhecida/vazia)."""
    area_atual = categorias.AREA_POR_CATEGORIA_ID.get(categoria_atual_id) if categoria_atual_id else None

    if not usar_ia:
        return ResultadoClassificacao(
            area=area_atual or _AREA_PADRAO, categoria_id=None, precisou_embedding=False
        )

    try:
        escolhida = await _melhor_categoria(ollama_client, modelo_embedding, titulo, descricao)
    except EmbeddingNaoSuportado:
        return ResultadoClassificacao(
            area=area_atual or _AREA_PADRAO,
            categoria_id=None,
            precisou_embedding=True,
            embedding_indisponivel=True,
        )
    except Exception:
        return ResultadoClassificacao(
            area=area_atual or _AREA_PADRAO, categoria_id=None, precisou_embedding=True
        )

    if escolhida.area == area_atual:
        return ResultadoClassificacao(area=area_atual, categoria_id=None, precisou_embedding=True)
    return ResultadoClassificacao(area=escolhida.area, categoria_id=escolhida.id, precisou_embedding=True)


async def _melhor_categoria(
    ollama_client: AsyncClient, modelo_embedding: str, titulo: str, descricao: str
) -> CategoriaGlpi:
    embeddings_categorias = await _embeddings_categorias_cacheados(ollama_client, modelo_embedding)
    embedding_chamado = await _gerar_embedding(ollama_client, modelo_embedding, f"{titulo}\n{descricao}")

    melhor = categorias.CATEGORIAS_ATRIBUIVEIS[0]
    melhor_similaridade = -2.0  # abaixo do mínimo possível (-1.0), garante que a 1a categoria sempre entra
    for categoria in categorias.CATEGORIAS_ATRIBUIVEIS:
        similaridade = _similaridade_cosseno(embedding_chamado, embeddings_categorias[categoria.id])
        if similaridade > melhor_similaridade:
            melhor_similaridade = similaridade
            melhor = categoria
    return melhor


async def _embeddings_categorias_cacheados(
    ollama_client: AsyncClient, modelo_embedding: str
) -> dict[int, list[float]]:
    global _cache_embeddings_categorias
    if _cache_embeddings_categorias is None:
        _cache_embeddings_categorias = {
            categoria.id: await _gerar_embedding(ollama_client, modelo_embedding, categoria.nome)
            for categoria in categorias.CATEGORIAS_ATRIBUIVEIS
        }
    return _cache_embeddings_categorias


async def _gerar_embedding(ollama_client: AsyncClient, modelo_embedding: str, texto: str) -> list[float]:
    resposta = await ollama_client.embed(model=modelo_embedding, input=texto)
    return list(resposta.embeddings[0])


# Duplicada de propósito (não importa de `tools/rh/similaridade.py`) — são
# ~10 linhas, e acoplar TI a RH por uma função tão pequena não compensa.
# Levar isso pra `agent/core.py` seria uma limpeza futura razoável se um
# terceiro módulo precisar da mesma conta.
def _similaridade_cosseno(vetor_a: list[float], vetor_b: list[float]) -> float:
    if len(vetor_a) != len(vetor_b):
        return 0.0
    produto_escalar = sum(a * b for a, b in zip(vetor_a, vetor_b, strict=True))
    norma_a = math.sqrt(sum(a * a for a in vetor_a))
    norma_b = math.sqrt(sum(b * b for b in vetor_b))
    if norma_a == 0 or norma_b == 0:
        return 0.0
    return produto_escalar / (norma_a * norma_b)
