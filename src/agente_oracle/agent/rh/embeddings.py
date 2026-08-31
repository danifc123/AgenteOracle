"""Geração de embedding pro RAG de candidatos do RH — chama o Ollama pra
transformar texto (currículo, descrição de vaga) num vetor. A comparação
desses vetores (similaridade de cosseno, sem IA) mora em
`tools/rh/similaridade.py`, não aqui."""

from ollama import AsyncClient


class AnaliseIndisponivel(Exception):
    """Levantada quando a IA do RH (chat ou embeddings) não consegue
    responder — Ollama fora do ar, modelo não baixado, resposta mal
    formada. Definida aqui (não em `perfil_candidato.py`/
    `busca_candidatos.py`) porque os dois já dependem deste módulo pra
    gerar embedding — evita duas classes de exceção diferentes com o
    mesmo propósito."""


async def gerar_embedding(ollama_client: AsyncClient, modelo_embedding: str, texto: str) -> list[float]:
    try:
        resposta = await ollama_client.embed(model=modelo_embedding, input=texto)
        return list(resposta.embeddings[0])
    except Exception as erro:
        raise AnaliseIndisponivel(
            "Não foi possível gerar o embedding com a IA no momento (confira se o modelo de "
            "embeddings está baixado no Ollama)."
        ) from erro
