from typing import Any

from mcp import ClientSession
from mcp.types import CallToolResult, Tool
from ollama import AsyncClient
from ollama import Message as OllamaMessage

ESQUEMA_FINANCEIRO = """
Tabelas disponíveis no banco Oracle (todas somente leitura):

- CONTAS_BANCARIAS(ID_CONTA PK, NOME_CONTA, BANCO, AGENCIA, NUMERO_CONTA, TIPO_CONTA[CORRENTE|POUPANCA|INVESTIMENTO], SALDO_ATUAL, DATA_ABERTURA)
- CATEGORIAS_FINANCEIRAS(ID_CATEGORIA PK, NOME_CATEGORIA, TIPO_CATEGORIA[RECEITA|DESPESA], DESCRICAO)
- FORNECEDORES_CLIENTES(ID_ENTIDADE PK, NOME, TIPO_ENTIDADE[FORNECEDOR|CLIENTE], CNPJ_CPF, EMAIL, TELEFONE)
- TRANSACOES(ID_TRANSACAO PK, ID_CONTA FK->CONTAS_BANCARIAS, ID_CATEGORIA FK->CATEGORIAS_FINANCEIRAS, ID_ENTIDADE FK->FORNECEDORES_CLIENTES [opcional], TIPO_TRANSACAO[ENTRADA|SAIDA], DESCRICAO, VALOR, DATA_TRANSACAO, STATUS_TRANSACAO[PAGO|PENDENTE|CANCELADO])
- FATURAS(ID_FATURA PK, ID_TRANSACAO FK->TRANSACOES, NUMERO_FATURA, DATA_EMISSAO, DATA_VENCIMENTO, DATA_PAGAMENTO, STATUS_FATURA[PAGA|EM_ABERTO|ATRASADA|CANCELADA])
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
- Depois de rodar a consulta, explique o resultado em português, de forma direta e objetiva.

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


async def _executar_chamadas_de_ferramenta(session: ClientSession, tool_calls: list) -> list[dict[str, Any]]:
    mensagens_resultado = []
    for chamada in tool_calls:
        nome = chamada.function.name
        argumentos = chamada.function.arguments or {}
        resultado = await session.call_tool(nome, argumentos)
        mensagens_resultado.append({"role": "tool", "content": _conteudo_do_resultado(resultado)})
    return mensagens_resultado


def _mensagem_para_historico(mensagem: OllamaMessage) -> dict[str, Any]:
    return mensagem.model_dump(exclude_none=True)


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

    while mensagem.tool_calls:
        for chamada in mensagem.tool_calls:
            eventos.append({"ferramenta": chamada.function.name, "argumentos": dict(chamada.function.arguments or {})})

        resultados = await _executar_chamadas_de_ferramenta(session, mensagem.tool_calls)
        messages.extend(resultados)
        resposta = await ollama_client.chat(model=modelo, messages=messages, tools=tools)
        mensagem = resposta.message
        messages.append(_mensagem_para_historico(mensagem))

    return messages, eventos
