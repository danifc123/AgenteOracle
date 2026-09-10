"""Similaridade de cosseno entre embeddings — sem `pgvector` (não disponível
no Postgres deste ambiente, uma instalação nativa Windows sem a extensão),
o vetor de cada candidato fica guardado como `JSONB` (lista de floats) numa
coluna normal (ver `tools/rh/candidatos.py`), e a comparação é calculada
aqui em Python puro — funciona bem pro tamanho de um pool de candidatos de
RH (não é o caso de precisar de milhares/milhões de vetores indexados).

Separado de `agent/rh/embeddings.py` (que gera o embedding via Ollama):
esta função não chama IA nenhuma, é matemática pura — mora em `tools/`
mesmo sendo consumida por `agent/rh/busca_candidatos.py`."""

import math


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
