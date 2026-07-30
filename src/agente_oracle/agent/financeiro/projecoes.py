"""Lógica pura das telas de Previsão (Vendas e Fluxo de Caixa) do Financeiro:
regressão linear simples pra projetar vendas futuras e a chamada de IA que
narra os números já calculados. Sem I/O de banco — as queries que alimentam
essas funções ficam em `server/financeiro/previsao.py`."""

import json

from ollama import AsyncClient

# Mesma constante de `financeiro.py` — evita reservar mais RAM do que essa
# análise curta precisa.
_OPCOES_OLLAMA = {"num_ctx": 16384}

# Mesmo estilo de `_RESPOSTA_TEXTO_SCHEMA` em `financeiro.py`: um schema
# mínimo, só com o campo de texto, pra IA nunca vazar JSON aninhado, tabela
# ou qualquer outro formato solto.
_SCHEMA_ANALISE = {
    "type": "object",
    "properties": {"analise": {"type": "string"}},
    "required": ["analise"],
}

_ANALISE_INDISPONIVEL = "Análise indisponível no momento."


def projetar_tendencia_linear(serie: list[float], meses_futuros: int) -> list[float]:
    """Projeta os próximos `meses_futuros` valores por regressão linear
    (mínimos quadrados) sobre `serie`, tratando cada posição como um mês
    sequencial (0, 1, 2, ...). Com menos de 2 pontos não há tendência
    possível de calcular, devolve lista vazia."""
    n = len(serie)
    if n < 2:
        return []

    soma_x = sum(range(n))
    soma_y = sum(serie)
    soma_xy = sum(indice * valor for indice, valor in enumerate(serie))
    soma_x2 = sum(indice * indice for indice in range(n))

    inclinacao = (n * soma_xy - soma_x * soma_y) / (n * soma_x2 - soma_x * soma_x)
    intercepto = (soma_y - inclinacao * soma_x) / n

    return [round(inclinacao * (n + passo) + intercepto, 2) for passo in range(meses_futuros)]


def proximos_meses(mes_referencia: str, quantidade: int) -> list[str]:
    """Gera os `quantidade` rótulos "YYYY-MM" seguintes a `mes_referencia`
    (também "YYYY-MM"), tratando virada de ano."""
    ano, mes = (int(parte) for parte in mes_referencia.split("-"))

    rotulos = []
    for _ in range(quantidade):
        mes += 1
        if mes > 12:
            mes = 1
            ano += 1
        rotulos.append(f"{ano:04d}-{mes:02d}")
    return rotulos


async def gerar_analise(ollama_client: AsyncClient, modelo: str, contexto: str) -> str:
    """Pede à IA uma análise textual curta em cima de números já calculados
    pelo Python (a IA nunca calcula a projeção nem inventa valor, só narra o
    que já veio pronto em `contexto`) — nunca deixa a tela quebrar: qualquer
    falha do Ollama ou resposta vazia cai numa frase neutra."""
    try:
        resposta = await ollama_client.chat(
            model=modelo,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é um analista financeiro. Escreva uma análise curta (2-3 frases), em "
                        "português, só com base nos números fornecidos — nunca invente ou arredonde "
                        "valores diferentes dos que aparecem no contexto."
                    ),
                },
                {"role": "user", "content": contexto},
            ],
            format=_SCHEMA_ANALISE,
            options=_OPCOES_OLLAMA,
        )
        analise = json.loads(resposta.message.content or "{}").get("analise")
        return analise or _ANALISE_INDISPONIVEL
    except Exception:
        return _ANALISE_INDISPONIVEL
