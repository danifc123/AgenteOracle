import json
import re
from typing import Any

from mcp import ClientSession
from mcp.types import CallToolResult, Tool
from ollama import AsyncClient
from ollama import Message as OllamaMessage

_TOOL_CALL_TAG_REGEX = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)

ESQUEMA_FINANCEIRO = """
Tabelas disponíveis no banco Oracle (todas somente leitura):

- CONTAS_BANCARIAS(ID_CONTA PK, NOME_CONTA, BANCO, AGENCIA, NUMERO_CONTA, TIPO_CONTA[CORRENTE|POUPANCA|INVESTIMENTO], SALDO_ATUAL, DATA_ABERTURA)
- CATEGORIAS_FINANCEIRAS(ID_CATEGORIA PK, NOME_CATEGORIA, TIPO_CATEGORIA[RECEITA|DESPESA], DESCRICAO)
- FORNECEDORES_CLIENTES(ID_ENTIDADE PK, NOME, TIPO_ENTIDADE[FORNECEDOR|CLIENTE], CNPJ_CPF, EMAIL, TELEFONE)
- TRANSACOES(ID_TRANSACAO PK, ID_CONTA FK->CONTAS_BANCARIAS, ID_CATEGORIA FK->CATEGORIAS_FINANCEIRAS, ID_ENTIDADE FK->FORNECEDORES_CLIENTES [opcional], ID_CENTRO_CUSTO FK->CENTROS_CUSTO [opcional], TIPO_TRANSACAO[ENTRADA|SAIDA], DESCRICAO, VALOR, DATA_TRANSACAO, STATUS_TRANSACAO[PAGO|PENDENTE|CANCELADO])
- FATURAS(ID_FATURA PK, ID_TRANSACAO FK->TRANSACOES, NUMERO_FATURA, DATA_EMISSAO, DATA_VENCIMENTO, DATA_PAGAMENTO, STATUS_FATURA[PAGA|EM_ABERTO|ATRASADA|CANCELADA])
- CENTROS_CUSTO(ID_CENTRO_CUSTO PK, NOME_CENTRO_CUSTO, RESPONSAVEL, ATIVO[S|N])
- ORCAMENTOS(ID_ORCAMENTO PK, ID_CATEGORIA FK->CATEGORIAS_FINANCEIRAS, ID_CENTRO_CUSTO FK->CENTROS_CUSTO [opcional], ANO, MES, VALOR_PREVISTO) -- valor orçado por categoria/mês; para comparar orçado x realizado, some TRANSACOES.VALOR filtrando por ID_CATEGORIA/ano/mês e compare com VALOR_PREVISTO
""".strip()

SYSTEM_PROMPT = f"""Você é o Agente Oracle, um assistente do departamento financeiro. \
Use as ferramentas disponíveis para consultar dados e testar a conexão com o \
banco Oracle quando o usuário pedir.

{ESQUEMA_FINANCEIRO}

Quando o usuário pedir um relatório ou dado que não é coberto por uma ferramenta \
pronta, use a ferramenta `executar_consulta_financeira` para rodar uma consulta \
SELECT sobre as tabelas acima. Regras obrigatórias:
- Gere sempre SQL Oracle válido, somente SELECT (nunca INSERT/UPDATE/DELETE ou DDL).
- Use apenas as tabelas listadas acima, com JOIN quando precisar combinar dados.
- Nunca invente colunas ou tabelas fora do esquema acima.
- Sempre informe também um `titulo` curto e claro, em português, descrevendo o relatório \
(ex: "Transações de fornecedor X em março de 2026") — ele fica salvo no histórico de relatórios.
- Depois de rodar a consulta, explique o resultado em português, de forma direta e objetiva, \
usando SOMENTE os dados que a ferramenta devolveu. NUNCA invente, complete ou escreva \
valores/linhas que não vieram na resposta da ferramenta — isso vale mesmo se você "lembrar" \
de ter visto um relatório parecido antes: se não veio da ferramenta agora, não é real.
- Se a mesma consulta já tiver sido rodada antes, a ferramenta detecta isso sozinha (comparando \
o SQL) e devolve `reutilizado=true` com o resultado já salvo e a data em `gerado_em`, sem rodar \
de novo no Oracle — nesse caso, avise o usuário que esse relatório já tinha sido gerado antes.
- Se a ferramenta retornar um erro dizendo que a consulta não é possível (colunas ou junções \
que não existem, tabelas sem relação direta), NÃO fique tentando outras variações de SQL às \
cegas. Explique diretamente ao usuário, em português, que não é possível gerar esse relatório \
porque as tabelas pedidas não têm essa relação no banco.
- Se o usuário pedir dado que não existe em NENHUMA das tabelas listadas acima (ex: \
funcionários, RH, folha de pagamento, salários), NÃO tente aproximar a resposta usando outras \
tabelas nem especule sobre o assunto. Responda apenas, de forma direta, que você não tem \
acesso a essas informações.

Responda sempre em português."""


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


def _chamadas_normalizadas(mensagem: OllamaMessage) -> list[dict[str, Any]]:
    """Extrai as chamadas de ferramenta pedidas pelo modelo, cobrindo dois formatos:
    o mecanismo estruturado do Ollama (`mensagem.tool_calls`) e, como reforço, o
    formato em texto que o Qwen às vezes usa (`<tool_call>{"name":..,"arguments":..}</tool_call>`)
    quando não aciona o mecanismo estruturado — sem esse reforço, essas chamadas
    apareceriam como texto solto na resposta em vez de serem executadas."""
    if mensagem.tool_calls:
        return [
            {"nome": chamada.function.name, "argumentos": dict(chamada.function.arguments or {})}
            for chamada in mensagem.tool_calls
        ]

    chamadas = []
    for bloco in _TOOL_CALL_TAG_REGEX.findall(mensagem.content or ""):
        try:
            dados = json.loads(bloco)
        except json.JSONDecodeError:
            continue
        nome = dados.get("name")
        if nome:
            chamadas.append({"nome": nome, "argumentos": dados.get("arguments") or {}})
    return chamadas


async def _executar_chamadas_de_ferramenta(
    session: ClientSession, chamadas: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], str | None]:
    mensagens_resultado = []
    erro_tratado: str | None = None
    for chamada in chamadas:
        resultado = await session.call_tool(chamada["nome"], chamada["argumentos"])
        conteudo = _conteudo_do_resultado(resultado)
        mensagens_resultado.append({"role": "tool", "content": conteudo})
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

    resposta = await ollama_client.chat(model=modelo, messages=messages, tools=tools)
    mensagem = resposta.message
    messages.append(_mensagem_para_historico(mensagem))

    chamadas = _chamadas_normalizadas(mensagem)
    while chamadas:
        for chamada in chamadas:
            eventos.append({"ferramenta": chamada["nome"], "argumentos": chamada["argumentos"]})

        resultados, erro_tratado = await _executar_chamadas_de_ferramenta(session, chamadas)
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

    return messages, eventos
