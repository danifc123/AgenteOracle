"""Embeddings pro RAG de candidatos do RH — sem `pgvector` (não disponível
no Postgres deste ambiente, uma instalação nativa Windows sem a extensão),
o vetor de cada candidato fica guardado como `JSONB` (lista de floats)
numa coluna normal (ver `tools/rh/candidatos.py`), e a similaridade é
calculada aqui em Python puro — funciona bem pro tamanho de um pool de
candidatos de RH (não é o caso de precisar de milhares/milhões de vetores
indexados)."""

import math

from ollama import AsyncClient


class AnaliseIndisponivel(Exception):
    """Levantada quando a IA do RH (chat ou embeddings) não consegue
    responder — Ollama fora do ar, modelo não baixado, resposta mal
    formada. Definida aqui (não em `perfil_candidato.py`/
    `busca_candidatos.py`) porque os dois já dependem deste módulo pra
    gerar embedding — evita duas classes de exceção diferentes com o
    mesmo propósito."""


def similaridade_cosseno(vetor_a: list[float], vetor_b: list[float]) -> float:
    """1.0 = vetores idênticos em direção, 0.0 = ortogonais (sem relação),
    -1.0 = opostos. Devolve 0.0 se algum vetor for nulo (norma zero) ou se os
    dois tiverem dimensões diferentes (candidato embedado com um
    `ollama_embedding_model` antigo, antes do modelo configurado ter mudado)
    em vez de dividir por zero ou levantar erro — não deveria acontecer com
    embedding de verdade, mas evita derrubar a busca inteira por causa de um
    dado esquisito."""
    if len(vetor_a) != len(vetor_b):
        return 0.0
    produto_escalar = sum(a * b for a, b in zip(vetor_a, vetor_b, strict=True))
    norma_a = math.sqrt(sum(a * a for a in vetor_a))
    norma_b = math.sqrt(sum(b * b for b in vetor_b))
    if norma_a == 0 or norma_b == 0:
        return 0.0
    return produto_escalar / (norma_a * norma_b)


async def gerar_embedding(ollama_client: AsyncClient, modelo_embedding: str, texto: str) -> list[float]:
    try:
        resposta = await ollama_client.embed(model=modelo_embedding, input=texto)
        return list(resposta.embeddings[0])
    except Exception as erro:
        raise AnaliseIndisponivel(
            "Não foi possível gerar o embedding com a IA no momento (confira se o modelo de "
            "embeddings está baixado no Ollama)."
        ) from erro
