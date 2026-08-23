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

import re
from datetime import date, datetime
from decimal import Decimal

from starlette.requests import Request
from starlette.responses import JSONResponse

from agente_oracle.config import settings
from agente_oracle.server.auth.dependencia import exigir_modulo_financeiro
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.auth import restricoes_filial
from agente_oracle.tools.ti import acessos_dados

# Casa toda ocorrência textual de `:bind IS NULL OR :bind = ''` (o padrão de
# filtro opcional escrito à mão na maioria dos relatórios, sem passar por
# `filtro_vazio()`) — usado por `aplicar_cast_binds_opcionais()` abaixo.
_BIND_OPCIONAL_REGEX = re.compile(r":(\w+) IS NULL OR :\1 = ''")


def exigir_filiais_liberadas(request: Request) -> dict | JSONResponse:
    """Mesma checagem de `exigir_modulo_financeiro`, mais a exigência de que
    nenhuma filial pedida em `?filial=` esteja bloqueada pro usuário logado
    (`tools/auth/restricoes_filial.py`) — usada em todo relatório/exportação
    do Financeiro que filtra por filial, pra que o coordenador consiga
    restringir o acesso de alguém a uma filial específica mesmo que ela
    tenha acesso ao módulo como um todo.

    Lê `?filial=` direto da query string (em vez de reusar
    `filiais_da_query`, que já descarta a diferença entre "não informado" e
    "lista vazia") — isso cobre de graça toda rota que usa esse mesmo nome
    de parâmetro, inclusive `relatorio_customizado_sql.py`, que faz o
    próprio parsing e não passa por `filiais_da_query`."""
    resultado = exigir_modulo_financeiro(request)
    if isinstance(resultado, JSONResponse):
        return resultado

    bruto = request.query_params.get("filial", "").strip()
    filiais_pedidas = {item.strip() for item in bruto.split(",") if item.strip()}
    if not filiais_pedidas:
        return resultado

    bloqueadas = restricoes_filial.filiais_bloqueadas(int(resultado["sub"]), "financeiro")
    if filiais_pedidas & bloqueadas:
        return JSONResponse(
            {"erro": "Você não tem acesso a uma ou mais filiais selecionadas."},
            status_code=403,
            headers=CORS_HEADERS,
        )
    return resultado


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
    quebra contra Oracle.

    PEGADINHA IRMÃ, só contra Postgres (`desvio_margem.py` foi onde apareceu
    primeiro): se o bind só aparece dentro do `filtro_vazio()` e numa
    comparação de coluna mais adiante na mesma cláusula (ex:
    `({filtro_vazio("produto")} OR produto_codigo = :produto)`), o Postgres
    às vezes não consegue inferir o tipo do parâmetro em modo prepared
    statement (`psycopg.errors.AmbiguousParameter: could not determine data
    type`) — mesmo a comparação com a coluna real estando ali do lado.
    Confirmado rodando de verdade. Não acontece contra Oracle. Resolve
    dando um CAST explícito no bind em pelo menos um dos usos, com
    `texto_coluna()` (abaixo) — ver `desvio_margem.py::_buscar_desvios`
    pro padrão completo.

    Pra relatório NOVO, prefira `aplicar_cast_binds_opcionais()` (abaixo) em
    vez de montar essa expressão à mão — ela já resolve a pegadinha sozinha,
    sem precisar lembrar de qual bind castar."""
    return f"(:{bind} IS NULL OR :{bind} = '')"


def aplicar_cast_binds_opcionais(sql: str) -> str:
    """Aplica de uma vez, em toda a query, o mesmo CAST que resolve a
    "pegadinha irmã" documentada em `filtro_vazio()` — sem precisar caçar
    manualmente qual bind precisa (é fácil esquecer um: `desvio_margem.py`
    tinha 1, `contas_receber_produto.py` tinha 4 espalhados, cada um exigindo
    seu próprio CAST mesmo repetindo o mesmo bind).

    Acha toda ocorrência textual de `:bind IS NULL OR :bind = ''` (o padrão
    escrito à mão em quase todo `_QUERY` deste pacote) e insere
    `CAST(:bind AS TEXT)` no primeiro `:bind`. Chame no fim de
    `_buscar_*()`, depois de todos os `.replace()` de placeholder de SQL,
    assim: `sql = _comum.aplicar_cast_binds_opcionais(sql)`.

    No Oracle é um no-op puro (a função devolve a SQL sem tocar, nem roda a
    regex) — a query já funciona sem CAST lá, então não tem custo nem risco
    de mudar comportamento no banco real."""
    if settings.db_backend != "postgres":
        return sql
    return _BIND_OPCIONAL_REGEX.sub(
        lambda m: f"CAST(:{m.group(1)} AS TEXT) IS NULL OR :{m.group(1)} = ''", sql
    )


def numero_bind(bind: str) -> str:
    """Bind `:bind` (texto vindo da tela) -> número comparável. Precisão/escala
    explícitas porque o `NUMERIC` "puro" do Oracle (sem parâmetros) trunca pra
    inteiro — diferente do Postgres, onde `NUMERIC` sem parâmetros já é
    decimal de precisão arbitrária."""
    if settings.db_backend == "postgres":
        return f"CAST(:{bind} AS NUMERIC)"
    return f"CAST(:{bind} AS NUMBER(28,6))"


def numero_coluna(expressao: str) -> str:
    """Coluna/expressão (texto ou já numérica) -> número. Substitui
    `TO_NUMBER(expressao)`/`CAST(expressao AS NUMBER)` escrito à mão — os
    dois são sintaxe **exclusiva do Oracle** (confirmado rodando contra o
    Postgres fictício: `TO_NUMBER` de 1 argumento não existe lá — o do
    Postgres exige uma máscara de formato como segundo argumento, e o tipo
    `NUMBER` também não existe, é `NUMERIC`). Achado em
    `movimento_financeiro_diario.py`/`relacao_baixas.py`/
    `fluxo_caixa_realizado.py` ao popular o banco fictício com
    `saldobancario`/`movimentacaofinanceira` — não tinha aparecido antes
    porque nenhum desses relatórios tinha sido testado contra Postgres."""
    if settings.db_backend == "postgres":
        return f"CAST({expressao} AS NUMERIC)"
    return f"TO_NUMBER({expressao})"


def texto_numero(expressao: str) -> str:
    """Coluna/expressão numérica -> texto. `TO_CHAR(expressao)` de 1
    argumento (sem máscara) é sintaxe **exclusiva do Oracle**: o `TO_CHAR`
    do Postgres não tem overload de 1 argumento pra `numeric` (só pra
    `timestamp`) — exige uma máscara de formato como segundo argumento.
    Achado nos JOINs com `STAGE.bancobacen` (`TO_CHAR(bb.codigo) =
    LPAD(...)`) em `movimento_financeiro_diario.py`/`relacao_baixas.py` ao
    popular o banco fictício."""
    if settings.db_backend == "postgres":
        return f"CAST({expressao} AS TEXT)"
    return f"TO_CHAR({expressao})"


def origem_linha_unica() -> str:
    """`SELECT ... {origem_linha_unica()}` pra montar uma linha "solta" (sem
    tabela de origem, ex: uma constante numa CTE tipo `meses` de
    `fluxo_caixa_realizado.py`) — Oracle exige `FROM DUAL`; Postgres aceita
    `SELECT` sem `FROM` nenhum (e não tem uma tabela `DUAL` por padrão —
    confirmado rodando: `relation "dual" does not exist`)."""
    if settings.db_backend == "postgres":
        return ""
    return " FROM DUAL"


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


def registrar_acesso(usuario: dict, recurso: str, quantidade: int) -> None:
    """Loga quem exportou/listou o quê e quantos registros vieram —
    pré-requisito pro agente de detecção de segurança do módulo TI
    (`agent/ti/deteccao_seguranca.py`) ter volume de acesso a dado real pra
    analisar. Chamar logo antes de devolver a resposta, no ponto em que a
    quantidade de linhas já é conhecida."""
    acessos_dados.registrar(usuario["sub"], "financeiro", recurso, quantidade)


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
