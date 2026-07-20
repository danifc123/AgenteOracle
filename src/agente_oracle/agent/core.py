import json
import re
from typing import Any

from mcp import ClientSession
from mcp.types import CallToolResult, Tool
from ollama import AsyncClient
from ollama import Message as OllamaMessage

_TOOL_CALL_TAG_REGEX = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)

# Detecta quando o modelo narrou uma consulta em vez de chamar a ferramenta de
# verdade — seja como bloco de código com SELECT, seja como pseudo-chamada de
# função em texto (ex: "executar_consulta_financeira(sql=...)" fora do
# mecanismo estruturado de tool-calling). Isso faz parecer que um relatório
# foi gerado quando na prática nenhuma consulta rodou no banco.
_SQL_NARRADO_REGEX = re.compile(
    r"```[a-zA-Z]*\s*\n[^`]*?\bSELECT\b|\bexecutar_consulta_financeira\s*\(",
    re.IGNORECASE | re.DOTALL,
)

_AVISO_SQL_NARRADO = (
    "Você descreveu uma consulta em texto (ou pseudo-SQL) em vez de chamar a "
    "ferramenta executar_consulta_financeira. O usuário só recebe o relatório de "
    "verdade se a ferramenta for executada — se a pergunta precisa de dados reais, "
    "chame a ferramenta agora com o SQL de verdade, em vez de descrever a consulta em texto."
)

# Pega valores em R$ citados na resposta final do modelo, pra conferir se eles
# realmente vieram do resultado de uma consulta (ver `_resposta_fundamentada`).
_VALOR_MONETARIO_REGEX = re.compile(r"R\$\s*([\d][\d.,]*\d)")


def mcp_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/mcp"


def tools_para_ollama(mcp_tools: list[Tool]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        }
        for tool in mcp_tools
    ]


def _conteudo_do_resultado(resultado: CallToolResult) -> str:
    partes = [bloco.text for bloco in resultado.content if getattr(bloco, "text", None)]
    return "\n".join(partes) if partes else str(resultado)


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
    """Resposta neutra usada quando a resposta do modelo cita um valor em R$
    que não bate com nenhum dado real retornado — mais seguro devolver isso
    do que arriscar mostrar um número inventado num contexto financeiro."""
    ultimo = next(
        (evento for evento in reversed(eventos) if "titulo" in evento["argumentos"]),
        None,
    )
    if ultimo:
        titulo = ultimo["argumentos"]["titulo"]
        return (
            f'Gerei o relatório "{titulo}" com os dados encontrados. '
            "Os valores certos estão na tabela/Excel do relatório — evitei repetir números "
            "aqui em texto pra não arriscar errar algum ao resumir."
        )
    return "Consulta executada com sucesso — confira os dados retornados no relatório gerado."


def _chamada_do_bloco_json(bloco: str) -> dict[str, Any] | None:
    try:
        dados = json.loads(bloco)
    except json.JSONDecodeError:
        return None
    nome = dados.get("name")
    if not nome:
        return None
    return {"nome": nome, "argumentos": dados.get("arguments") or {}}


def _blocos_json_balanceados(texto: str) -> list[str]:
    """Encontra todos os blocos `{...}` bem-balanceados no texto, contando
    chaves — funciona independente de estarem dentro de cerca de código, de
    uma tag <tool_call> ou soltos no meio da frase. Necessário porque algumas
    variantes do modelo (ex: "coder") são inconsistentes sobre COMO descrevem
    uma chamada de ferramenta quando não usam o mecanismo estruturado do
    Ollama — às vezes com cerca ```json, às vezes cru no meio do texto."""
    blocos = []
    profundidade = 0
    inicio = None
    for indice, caractere in enumerate(texto):
        if caractere == "{":
            if profundidade == 0:
                inicio = indice
            profundidade += 1
        elif caractere == "}":
            if profundidade > 0:
                profundidade -= 1
                if profundidade == 0 and inicio is not None:
                    blocos.append(texto[inicio : indice + 1])
                    inicio = None
    return blocos


def _chamadas_normalizadas(mensagem: OllamaMessage) -> list[dict[str, Any]]:
    """Extrai as chamadas de ferramenta pedidas pelo modelo. Prioriza o
    mecanismo estruturado do Ollama (`mensagem.tool_calls`) e, como reforço,
    varre o texto atrás de blocos `{"name":..,"arguments":..}` bem-formados —
    com ou sem a tag `<tool_call>`, com ou sem cerca de código ```json — que
    algumas variantes do modelo usam de forma inconsistente em vez do
    mecanismo estruturado. Sem esse reforço, essas chamadas apareceriam como
    texto solto na resposta em vez de serem executadas."""
    if mensagem.tool_calls:
        return [
            {"nome": chamada.function.name, "argumentos": dict(chamada.function.arguments or {})}
            for chamada in mensagem.tool_calls
        ]

    texto = mensagem.content or ""
    return [
        chamada
        for bloco in _blocos_json_balanceados(texto)
        if (chamada := _chamada_do_bloco_json(bloco)) is not None
    ]


async def _executar_chamadas_de_ferramenta(
    session: ClientSession,
    chamadas: list[dict[str, Any]],
    nomes_permitidos: set[str],
    eventos: list[dict[str, Any]],
    valores_fundamentados: set[float],
) -> tuple[list[dict[str, Any]], str | None]:
    """Executa as chamadas pedidas pelo modelo — mas só as que estão em
    `nomes_permitidos` (as tools que de fato foram oferecidas a ele neste turno).
    A sessão MCP em si enxerga as tools de todos os módulos registrados no
    mesmo servidor, então essa checagem é o que garante, na prática, que o
    agente de um módulo não acabe chamando a tool de outro — filtrar só a
    lista mostrada ao modelo não seria suficiente por si só.

    Cada chamada bem-sucedida vira um evento em `eventos` (nome + argumentos +
    quantas linhas vieram, quando aplicável) — usado pelo front pra mostrar o
    SQL usado e o botão de baixar Excel. Chamadas repetidas com exatamente os
    mesmos argumentos não duplicam o evento. Os valores numéricos do resultado
    alimentam `valores_fundamentados`, usado depois em `responder` pra
    conferir se a resposta final do modelo não está citando número inventado."""
    mensagens_resultado = []
    erro_tratado: str | None = None
    for chamada in chamadas:
        if chamada["nome"] not in nomes_permitidos:
            conteudo = f"Ferramenta '{chamada['nome']}' não está disponível neste contexto."
            mensagens_resultado.append({"role": "tool", "content": conteudo})
            if erro_tratado is None:
                erro_tratado = conteudo
            continue

        resultado = await session.call_tool(chamada["nome"], chamada["argumentos"])
        conteudo = _conteudo_do_resultado(resultado)
        mensagens_resultado.append({"role": "tool", "content": conteudo})
        valores_fundamentados.update(_valores_numericos_do_resultado(conteudo))

        evento = {
            "ferramenta": chamada["nome"],
            "argumentos": chamada["argumentos"],
            "linhas_retornadas": _linhas_retornadas(conteudo),
        }
        if evento not in eventos:
            eventos.append(evento)

        if resultado.isError and erro_tratado is None:
            erro_tratado = conteudo
    return mensagens_resultado, erro_tratado


def _mensagem_para_historico(mensagem: OllamaMessage) -> dict[str, Any]:
    dados = mensagem.model_dump(exclude_none=True)
    if dados.get("content"):
        dados["content"] = _TOOL_CALL_TAG_REGEX.sub("", dados["content"]).strip()
    return dados


async def responder(
    ollama_client: AsyncClient,
    modelo: str,
    session: ClientSession,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Roda um turno completo de chat (incluindo chamadas de ferramenta em loop,
    se o modelo pedir) e devolve o histórico de mensagens atualizado, terminando
    com a resposta final do assistente, junto com a lista de ferramentas chamadas
    nesse turno (nome + argumentos, ex: o SQL usado em executar_consulta_financeira)."""
    eventos: list[dict[str, Any]] = []
    valores_fundamentados: set[float] = set()
    nomes_permitidos = {tool["function"]["name"] for tool in tools}
    ja_cobrou_execucao_real = False

    resposta = await ollama_client.chat(model=modelo, messages=messages, tools=tools)
    mensagem = resposta.message
    messages.append(_mensagem_para_historico(mensagem))
    chamadas = _chamadas_normalizadas(mensagem)

    while True:
        if chamadas:
            resultados, erro_tratado = await _executar_chamadas_de_ferramenta(
                session, chamadas, nomes_permitidos, eventos, valores_fundamentados
            )
            messages.extend(resultados)

            if erro_tratado:
                # Devolve a mensagem de erro já tratada pela ferramenta direto pro usuário,
                # em vez de deixar o modelo reformular (e às vezes inventar) por cima dela.
                messages.append({"role": "assistant", "content": erro_tratado})
                return messages, eventos

            resposta = await ollama_client.chat(model=modelo, messages=messages, tools=tools)
            mensagem = resposta.message
            messages.append(_mensagem_para_historico(mensagem))
            chamadas = _chamadas_normalizadas(mensagem)
            continue

        # Sem nenhuma chamada de ferramenta neste turno: se o modelo nunca
        # executou nada e só narrou uma consulta em texto, cobra uma vez que
        # ele execute de verdade, em vez de devolver isso como resposta final
        # (senão o usuário vê algo parecido com um relatório sem ter recebido nada).
        if not eventos and not ja_cobrou_execucao_real and _SQL_NARRADO_REGEX.search(mensagem.content or ""):
            ja_cobrou_execucao_real = True
            messages.append({"role": "user", "content": _AVISO_SQL_NARRADO})
            resposta = await ollama_client.chat(model=modelo, messages=messages, tools=tools)
            mensagem = resposta.message
            messages.append(_mensagem_para_historico(mensagem))
            chamadas = _chamadas_normalizadas(mensagem)
            continue

        break

    if eventos:
        # Rede de segurança determinística: se a resposta final citar algum
        # valor em R$ que não bate com nenhum dado (nem soma de coluna) que
        # veio de verdade da consulta, troca por uma resposta neutra — não
        # depende do modelo seguir a instrução do prompt de não inventar número.
        valores_citados = _valores_monetarios_no_texto(mensagem.content or "")
        if valores_citados - valores_fundamentados:
            messages[-1]["content"] = _resposta_segura_generica(eventos)

    return messages, eventos
