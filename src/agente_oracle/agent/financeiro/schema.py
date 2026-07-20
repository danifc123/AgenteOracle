"""Schema financeiro que a IA tem permissão de consultar via
`executar_consulta_financeira` — fonte única de verdade compartilhada entre o
prompt do agente (`agent/financeiro/prompt.py`) e a validação de segurança da
tool de SQL livre (`tools/financeiro/consulta_livre.py`), pra nunca ficarem
dessincronizadas (o prompt prometendo uma view que a validação não libera, ou
vice-versa).

Fica vazio até as views financeiras serem criadas no banco (view + usuário
Oracle somente leitura restrito a elas, sem acesso às tabelas reais do
TOTVS) — enquanto isso, tanto o prompt quanto a validação tratam como
"nenhuma view liberada" e a IA não gera SQL nenhum.
"""

from dataclasses import dataclass

# Prefixo das tools MCP deste módulo (ex: "financeiro_executar_consulta_financeira").
# Usado tanto no registro das tools (server/financeiro/ia.py) quanto na hora de
# filtrar quais tools cada agente enxerga (agent/cli.py, server/financeiro/ia.py) —
# assim, quando outro módulo (Compras, RH...) registrar tools no mesmo servidor
# MCP, o agente do Financeiro continua só vendo e só podendo chamar as dele.
PREFIXO_TOOL: str = "financeiro_"


@dataclass(frozen=True)
class ColunaView:
    """Uma coluna de uma view financeira, com descrição curta pra IA entender o que ela guarda."""

    nome: str
    descricao: str


@dataclass(frozen=True)
class ViewFinanceira:
    """Uma view liberada para o agente consultar. `nome` precisa bater exatamente
    com o nome real da view no banco (Oracle deixa identificadores em maiúsculas
    por padrão, salvo uso de aspas)."""

    nome: str
    descricao: str
    colunas: tuple[ColunaView, ...]


VIEWS_DISPONIVEIS: tuple[ViewFinanceira, ...] = ()

NOMES_VIEWS_PERMITIDAS: frozenset[str] = frozenset(view.nome.upper() for view in VIEWS_DISPONIVEIS)
