"""Utilitários compartilhados entre os relatórios fixos de `relatorios/*.py` —
extraído porque `serializar`, `filiais_da_query` e `parametros_opcionais`
eram copiados byte-a-byte em praticamente todo arquivo do módulo.

Datas do Protheus (E1_VENCTO, E5_DATA, C5_EMISSAO...) são guardadas como
texto "YYYYMMDD" — mesmo no Oracle real, confirmado via `USER_TAB_COLUMNS`
(não é só um jeito do banco de teste). `TO_DATE(texto, 'YYYYMMDD')` é nativo
nos dois bancos (Oracle e Postgres), então os relatórios usam essa conversão
direto no SQL, sem precisar de branch por `DB_BACKEND` — só `pertence_lista`,
`numero_bind` e `texto_coluna` precisam, porque a sintaxe realmente diverge
entre os dois bancos nesses três casos.

ACHADO IMPORTANTE (2026-08): o padrão `:bind = ''` pra "filtro opcional não
informado" (usado em praticamente todo relatório) é um bug silencioso contra
Oracle real — Oracle não distingue string vazia de NULL: um bind de `""`
vira NULL, e o LITERAL `''` na própria query TAMBÉM é NULL (confirmado
rodando de verdade — `'' IS NULL` dá TRUE no Oracle). Ou seja
`COALESCE(:bind, '') = ''` NÃO resolve (vira `NULL = NULL`, ainda NULL,
ainda não-TRUE) — só `:bind IS NULL OR :bind = ''` funciona nos dois bancos:
no Oracle o `IS NULL` pega o caso (a comparação com `''` nunca dispara); no
Postgres (que preserva `''` como valor real, distinto de NULL) é o `= ''`
que pega. Resultado do bug antigo: qualquer relatório com um filtro opcional
em branco (o caso normal de uso) devolvia ZERO linhas sem erro nenhum —
passou despercebido porque o smoke test contra Oracle
(`test_relatorios_oracle_hml.py`) só checava `status_code == 200` + "é uma
lista", e lista vazia também é lista. Use `filtro_vazio()` abaixo em todo
filtro opcional novo."""

from datetime import date, datetime
from decimal import Decimal

from starlette.requests import Request

from agente_oracle.config import settings


def filiais_da_query(request: Request) -> list[str] | None:
    """Lê o parâmetro 'filial' (obrigatório, aceita múltiplas separadas por
    vírgula). Devolve None quando nenhuma filial foi informada."""
    bruto = request.query_params.get("filial", "").strip()
    filiais = [item.strip() for item in bruto.split(",") if item.strip()]
    return filiais or None


def filtro_vazio(bind: str) -> str:
    """`:bind` (filtro opcional vindo da tela) "não foi informado"? Use como
    `({_comum.filtro_vazio("campo")} OR condicao_real)` no lugar de
    `:campo = ''` — ver o "ACHADO IMPORTANTE" no docstring do módulo pra
    entender por que a comparação direta (e até `COALESCE(:campo, '') = ''`)
    quebra contra Oracle."""
    return f"(:{bind} IS NULL OR :{bind} = '')"


def numero_bind(bind: str) -> str:
    """Bind `:bind` (texto vindo da tela) -> número comparável. Precisão/escala
    explícitas porque o `NUMERIC` "puro" do Oracle (sem parâmetros) trunca pra
    inteiro — diferente do Postgres, onde `NUMERIC` sem parâmetros já é
    decimal de precisão arbitrária."""
    if settings.db_backend == "postgres":
        return f"CAST(:{bind} AS NUMERIC)"
    return f"CAST(:{bind} AS NUMBER(28,6))"


def parametros_opcionais(request: Request, campos: tuple[str, ...]) -> dict[str, str]:
    return {chave: request.query_params.get(chave, "").strip() for chave in campos}


def pertence_lista(expressao: str, bind: str, delimitador: str = "|") -> str:
    """`expressao` (já TRIM()ada) está na lista de valores separados por
    `delimitador` vinda do bind `:bind` (ex: "AB|FA") — equivalente por banco
    ao Postgres `= ANY(string_to_array(...))`, que o Oracle não tem."""
    if settings.db_backend == "postgres":
        return f"{expressao} = ANY (string_to_array(:{bind}, '{delimitador}'))"
    return (
        f"INSTR('{delimitador}' || :{bind} || '{delimitador}', "
        f"'{delimitador}' || {expressao} || '{delimitador}') > 0"
    )


def serializar(valor):
    """Converte pros tipos que `JSONResponse` sabe serializar sozinho:
    `Decimal` -> `float`, `datetime`/`date` -> texto ISO; passa o resto
    direto. `datetime`/`date` só passou a aparecer aqui depois da migração
    pro STAGE — datas do Protheus cru vinham sempre como texto "YYYYMMDD",
    mas `STAGE.CONTARECEBER`/`MOVIMENTACAOFINANCEIRA`/etc. têm `TIMESTAMP`
    de verdade, que o driver do Oracle devolve como `datetime` do Python."""
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    return valor


def texto_coluna(expressao: str) -> str:
    """Coluna/expressão -> texto comparável. Postgres usa `TEXT`; Oracle não
    tem esse tipo, usa `VARCHAR2`."""
    if settings.db_backend == "postgres":
        return f"CAST({expressao} AS TEXT)"
    return f"CAST({expressao} AS VARCHAR2(4000))"
