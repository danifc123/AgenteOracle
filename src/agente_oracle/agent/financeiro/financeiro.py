"""Lógica do agente de IA do módulo Financeiro: como ele decide o que fazer
com a pergunta do usuário e como monta a resposta final. Específico deste
módulo — um futuro módulo de RH/Compras teria seu próprio arquivo equivalente
a este, reaproveitando só os utilitários genéricos de `agent/core.py`."""

import json
import re
from typing import Any

from mcp import ClientSession
from ollama import AsyncClient

from agente_oracle.agent.core import conteudo_do_resultado

# O Ollama reserva RAM proporcional ao tamanho de contexto configurado, e o
# padrão dele (65536 tokens) é muito maior do que qualquer conversa aqui
# precisa — nosso system prompt + histórico + resultado de consulta cabem
# folgados bem abaixo disso. Numa máquina com pouca RAM livre, esse exagero
# pode fazer o Ollama estourar memória e reiniciar sozinho no meio de uma
# resposta. 16384 dá espaço de sobra (inclusive pra um relatório grande, até
# o limite de 200 linhas) consumindo uma fração da memória.
_OPCOES_OLLAMA = {"num_ctx": 16384}

# Formato forçado da decisão do modelo (ver `responder`). Em vez do mecanismo
# de tool-calling em texto livre do Ollama — onde o modelo podia "esquecer"
# de chamar a ferramenta e responder com SQL narrado, tabela fabricada, JSON
# solto ou uma frase copiada do prompt, todos bugs reais que apareceram no
# desenvolvimento — o decodificador do Ollama é obrigado a preencher
# exatamente estes campos, sempre nesse formato. O modelo ainda pode errar o
# CONTEÚDO (decidir não consultar quando devia), mas nunca mais erra o
# FORMATO da resposta.
_DECISAO_SCHEMA = {
    "type": "object",
    "properties": {
        "acao": {
            "type": "string",
            "enum": ["consultar_dados", "testar_conexao", "responder_direto"],
        },
        "sql": {"type": ["string", "null"]},
        "titulo": {"type": ["string", "null"]},
        "resposta_direta": {"type": ["string", "null"]},
    },
    "required": ["acao", "sql", "titulo", "resposta_direta"],
}

# Formato forçado da segunda chamada, usada só quando a pergunta era direta
# (ex: "quantos títulos em aberto") e precisa do resultado real da consulta
# pra ser respondida em palavras — um schema ainda mais simples, sem espaço
# pra vazar tabela ou JSON aninhado, só um campo de texto.
_RESPOSTA_TEXTO_SCHEMA = {
    "type": "object",
    "properties": {"resposta": {"type": "string"}},
    "required": ["resposta"],
}

# Presença de função de agregação indica uma pergunta direta (precisa do
# valor real pra responder em texto). Sem agregação, é uma listagem/relatório
# simples (ex: "me mostra os títulos de X"), cuja confirmação final é gerada
# 100% pelo código — nunca precisa perguntar pro modelo "o que você achou".
_AGREGACAO_SQL_REGEX = re.compile(r"\b(COUNT|SUM|AVG|MAX|MIN)\s*\(", re.IGNORECASE)

# Pega valores em R$ citados na resposta final do modelo, pra conferir se eles
# realmente vieram do resultado de uma consulta (ver `_resposta_fundamentada`).
_VALOR_MONETARIO_REGEX = re.compile(r"R\$\s*([\d][\d.,]*\d)")


def _linhas_retornadas(conteudo: str) -> int | None:
    """Extrai quantas linhas de dado vieram no resultado da ferramenta, quando
    o formato permite (hoje só `executar_consulta_financeira` devolve uma
    chave "dados" com a lista de linhas) — usado pelo front pra não oferecer
    o download de um relatório vazio. Devolve None quando não dá pra saber."""
    try:
        corpo = json.loads(conteudo)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(corpo, dict) and isinstance(corpo.get("dados"), list):
        return len(corpo["dados"])
    return None


def _normalizar_valor_monetario(bruto: str) -> float | None:
    """Interpreta um número monetário em texto livre aceitando tanto o formato
    brasileiro (1.234,56) quanto o americano (1,234.56), que o modelo às vezes
    mistura — o separador decimal é sempre o que aparece por último na string."""
    ultimo_ponto = bruto.rfind(".")
    ultima_virgula = bruto.rfind(",")
    limpo = bruto.replace(".", "").replace(",", ".") if ultima_virgula > ultimo_ponto else bruto.replace(",", "")
    try:
        return round(float(limpo), 2)
    except ValueError:
        return None


def _valores_monetarios_no_texto(texto: str) -> set[float]:
    valores = set()
    for bruto in _VALOR_MONETARIO_REGEX.findall(texto):
        valor = _normalizar_valor_monetario(bruto)
        if valor is not None:
            valores.add(valor)
    return valores


def _valores_numericos_do_resultado(conteudo: str) -> set[float]:
    """Extrai todo valor numérico que veio de fato de um resultado de
    `executar_consulta_financeira` — cada valor de cada linha, mais a soma de
    cada coluna numérica (pra cobrir respostas do tipo "o total foi X") — pra
    servir de base de comparação contra o que o modelo cita na resposta final."""
    try:
        corpo = json.loads(conteudo)
    except (json.JSONDecodeError, TypeError):
        return set()
    dados = corpo.get("dados") if isinstance(corpo, dict) else None
    if not isinstance(dados, list):
        return set()

    valores: set[float] = set()
    somas_por_coluna: dict[str, float] = {}
    for linha in dados:
        if not isinstance(linha, dict):
            continue
        for coluna, valor in linha.items():
            if isinstance(valor, bool) or not isinstance(valor, (int, float)):
                continue
            valor_float = round(float(valor), 2)
            valores.add(valor_float)
            somas_por_coluna[coluna] = somas_por_coluna.get(coluna, 0.0) + valor_float

    valores.update(round(soma, 2) for soma in somas_por_coluna.values())
    return valores


def _resposta_segura_generica(eventos: list[dict[str, Any]]) -> str:
    """Resposta neutra e curta usada quando a resposta do modelo pra uma
    pergunta direta cita um valor em R$ que não bate com o dado real — mais
    seguro devolver um texto simples do que arriscar mostrar algo errado num
    contexto financeiro. A consulta usada já fica visível em "Ver consulta
    usada" e o resultado no Excel, então não precisa repetir nada disso aqui."""
    ultimo = next(
        (evento for evento in reversed(eventos) if "titulo" in evento["argumentos"]),
        None,
    )
    if ultimo:
        titulo = ultimo["argumentos"]["titulo"]
        return f'Relatório "{titulo}" pronto — baixe em Excel abaixo.'
    return "Consulta executada com sucesso — confira os dados retornados no relatório gerado."


async def responder(
    ollama_client: AsyncClient,
    modelo: str,
    session: ClientSession,
    nome_tool_consulta: str,
    nome_tool_teste_conexao: str,
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Roda um turno de chat do agente Financeiro usando saída estruturada
    (JSON forçado pelo Ollama via `format`) em vez do mecanismo de
    tool-calling em texto livre — o modelo sempre decide entre
    `consultar_dados` / `testar_conexao` / `responder_direto` nesse formato
    fixo, então não tem mais como ele "esquecer" o formato certo (SQL
    narrado, tabela fabricada, JSON vazando, frase copiada do prompt — bugs
    reais que esse redesenho elimina estruturalmente, não só detecta).

    Devolve o histórico de mensagens atualizado (terminando na resposta final
    do assistente) e a lista de eventos (ferramenta + argumentos + linhas
    retornadas) desse turno, usada pelo front pra mostrar a consulta usada e
    o botão de baixar Excel."""
    eventos: list[dict[str, Any]] = []

    resposta = await ollama_client.chat(
        model=modelo, messages=messages, format=_DECISAO_SCHEMA, options=_OPCOES_OLLAMA
    )
    try:
        decisao = json.loads(resposta.message.content or "{}")
    except json.JSONDecodeError:
        decisao = {}

    acao = decisao.get("acao")

    if acao == "testar_conexao":
        resultado = await session.call_tool(nome_tool_teste_conexao, {})
        conteudo = conteudo_do_resultado(resultado)
        eventos.append({"ferramenta": nome_tool_teste_conexao, "argumentos": {}, "linhas_retornadas": None})
        messages.append({"role": "assistant", "content": conteudo})
        return messages, eventos

    if acao == "consultar_dados" and decisao.get("sql"):
        sql = decisao["sql"]
        titulo = decisao.get("titulo") or "Relatório"
        resultado = await session.call_tool(nome_tool_consulta, {"sql": sql, "titulo": titulo})
        conteudo = conteudo_do_resultado(resultado)
        linhas = _linhas_retornadas(conteudo)
        eventos.append(
            {
                "ferramenta": nome_tool_consulta,
                "argumentos": {"sql": sql, "titulo": titulo},
                "linhas_retornadas": linhas,
            }
        )

        if resultado.isError:
            messages.append({"role": "assistant", "content": conteudo})
            return messages, eventos

        if not linhas:
            messages.append({"role": "assistant", "content": "Não encontrei nenhum registro com esses critérios."})
            return messages, eventos

        if _AGREGACAO_SQL_REGEX.search(sql):
            # Pergunta direta (ex: "quantos..."): pede uma segunda resposta,
            # agora com o resultado real na mão, num formato ainda mais
            # simples e travado (só um campo de texto) — sem chance de vazar
            # SQL, tabela ou JSON aninhado, só o valor pedido.
            messages.append({"role": "tool", "content": conteudo})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Esse é o resultado real da consulta. Responda a pergunta original em português, "
                        "usando só o que veio literalmente nesse resultado — nunca invente número."
                    ),
                }
            )
            resposta2 = await ollama_client.chat(
                model=modelo, messages=messages, format=_RESPOSTA_TEXTO_SCHEMA, options=_OPCOES_OLLAMA
            )
            try:
                texto_final = json.loads(resposta2.message.content or "{}").get("resposta")
            except json.JSONDecodeError:
                texto_final = None

            valores_fundamentados = _valores_numericos_do_resultado(conteudo)
            if not texto_final or (_valores_monetarios_no_texto(texto_final) - valores_fundamentados):
                # Rede de segurança determinística: se a resposta citar algum
                # valor em R$ que não bate com nenhum dado (nem soma de
                # coluna) real, ou vier vazia, troca por uma resposta neutra
                # — não depende do modelo seguir instrução nenhuma pra isso.
                texto_final = _resposta_segura_generica(eventos)
        else:
            # Listagem simples: a confirmação é sempre gerada pelo código, sem
            # precisar perguntar pro modelo — mais rápido (economiza uma
            # chamada inteira) e sem risco nenhum de alucinação aqui.
            texto_final = f'Excel gerado com sucesso, baixe ele abaixo: "{titulo}".'

        messages.append({"role": "assistant", "content": texto_final})
        return messages, eventos

    texto = decisao.get("resposta_direta") or "Não entendi seu pedido, pode reformular?"
    messages.append({"role": "assistant", "content": texto})
    return messages, eventos
