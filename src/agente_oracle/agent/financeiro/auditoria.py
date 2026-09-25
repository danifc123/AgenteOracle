"""Provedor de auditoria de dados do módulo Financeiro — monta os perfis
(`agent/auditoria/perfil_campo.py`) que alimentam a análise genérica
(`agent/auditoria/analise.py`). Só sabe consultar as views já declaradas em
`schema.py`; não conhece a lógica de análise nem o esquema JSON da IA.

Conjunto inicial de campos checados: `filial` (o exemplo que motivou a
feature — filiais deveriam seguir um padrão de numeração), `estado`
(deveria ser sempre sigla de 2 letras — `agent/financeiro/schema.py` já tem
uma regra de prompt alertando a IA a nunca aceitar nome completo de estado
aqui, sinal de que já apareceu dado errado nesse campo), `tipo_pessoa` (só
deveria ser 'F' ou 'J') e `cnpj_cpf` (comprimento deveria ser 11 pra pessoa
física e 14 pra jurídica).

`construir_achados_desvio_margem` (2026-08) é um segundo tipo de provedor
pro mesmo módulo — em vez de montar perfil pra IA julgar, já entrega
`Achado` pronto, calculado 100% por SQL (mesma lógica de
`server/financeiro/relatorios/desvio_margem.py`, sem IA — margem é conta
objetiva, não julgamento). Os dois tipos alimentam o mesmo
`GET /api/auditoria` (`server/auditoria/rotas.py`), então acabam no mesmo
sino/painel/histórico, sem distinção nenhuma pro usuário final."""

from datetime import date, timedelta

from agente_oracle.agent.auditoria.analise import Achado
from agente_oracle.agent.auditoria.perfil_campo import PerfilCampo
from agente_oracle.db.connection import get_connection
from agente_oracle.server.financeiro.relatorios import _comum

_MODULO = "financeiro"

# Só vendas recentes (não o histórico inteiro) e só desvio relevante — uma
# margem 15 pontos percentuais ou mais ABAIXO da média do produto.
_DIAS_JANELA_DESVIO_MARGEM = 30
_LIMIAR_DESVIO_PERCENTUAL = -15.0

# `filial` existe (e deveria seguir o mesmo padrão de numeração) nessas
# views de título/faturamento; cadastro (vwia_clientes/vwia_fornecedores) não
# tem coluna `filial` no STAGE — só `estado`/`tipo_pessoa`/`cnpj_cpf`.
_VIEWS_COM_FILIAL = (
    "vwia_titulos_pagar",
    "vwia_titulos_receber",
    "vwia_faturamento",
)
_VIEWS_CADASTRO = ("vwia_clientes", "vwia_fornecedores")

# Protege o num_ctx do Ollama (16384, mesma constante usada no resto do
# projeto) de estourar se um campo que devia ser baixa cardinalidade não for,
# na prática, por dado sujo.
LIMITE_VALORES_POR_PERFIL = 50
LIMITE_EXEMPLOS_CNPJ_POR_GRUPO = 3


def construir_achados_desvio_margem() -> list[Achado]:
    """Vendas dos últimos `_DIAS_JANELA_DESVIO_MARGEM` dias cuja margem está
    `_LIMIAR_DESVIO_PERCENTUAL` pontos (ou mais) abaixo da média do mesmo
    produto — mesma lógica de `server/financeiro/relatorios/
    desvio_margem.py`, sem filtro de filial (auditoria não é escopada por
    filial, mesmo padrão de `construir_perfis_financeiro`), já filtrando
    pelo limiar no próprio SQL."""
    sql = """
        WITH linhas AS (
            SELECT nota_fiscal, serie, item_nota, produto_codigo, produto_descricao,
                   valor_total, custo
            FROM vwia_faturamento
            WHERE data_emissao >= :desde AND valor_total > 0
        ),
        com_desvio AS (
            SELECT nota_fiscal, serie, item_nota, produto_codigo, produto_descricao,
                   ROUND((valor_total - custo) / valor_total * 100, 2) AS margem_percentual,
                   ROUND(
                       ((valor_total - custo) / valor_total * 100)
                       - AVG((valor_total - custo) / valor_total * 100) OVER (PARTITION BY produto_codigo),
                       2
                   ) AS desvio_percentual
            FROM linhas
        )
        SELECT nota_fiscal, serie, item_nota, produto_codigo, produto_descricao,
               margem_percentual, desvio_percentual
        FROM com_desvio
        WHERE desvio_percentual <= :limiar
        ORDER BY desvio_percentual ASC
    """
    desde = date.today() - timedelta(days=_DIAS_JANELA_DESVIO_MARGEM)
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, desde=desde, limiar=_LIMIAR_DESVIO_PERCENTUAL)
        linhas = cursor.fetchall()
    return _achados_a_partir_das_linhas(linhas)


def _achados_a_partir_das_linhas(linhas: list[tuple]) -> list[Achado]:
    """Função pura (sem SQL) só pra `construir_achados_desvio_margem` ficar
    testável sem banco — um `Achado` por venda, `valor` identificando a
    nota/item específica (não o código de produto sozinho, que repetiria
    pra toda venda daquele produto e quebraria o dedup de
    `ja_identificados`)."""
    achados = []
    for nota_fiscal, serie, item_nota, produto_codigo, produto_descricao, margem, desvio in linhas:
        achados.append(
            Achado(
                modulo=_MODULO,
                view="vwia_faturamento",
                campo="desvio_percentual",
                valor=f"NF {nota_fiscal}/{serie} item {item_nota}",
                descricao=(
                    f"{produto_descricao} ({produto_codigo}): margem de {margem:.1f}%, "
                    f"{abs(desvio):.1f} pontos abaixo da média desse produto"
                ),
            )
        )
    return achados


def construir_perfis_financeiro() -> list[PerfilCampo]:
    perfis = [_perfil_distinto(view, "filial") for view in _VIEWS_COM_FILIAL]
    for view in _VIEWS_CADASTRO:
        perfis.append(_perfil_distinto(view, "estado"))
        perfis.append(_perfil_distinto(view, "tipo_pessoa"))
        perfis.append(_perfil_cnpj_cpf(view))
    return perfis


def _perfil_cnpj_cpf(view: str) -> PerfilCampo:
    """Perfil derivado: agrupa por (tipo_pessoa, comprimento do documento) em
    vez do valor bruto — com poucos exemplos mascarados por grupo, pra IA ter
    um valor real e citável (o comprimento mascarado continua visível) sem
    vazar o documento inteiro."""
    sql_grupos = f"""
        SELECT tipo_pessoa, LENGTH(cnpj_cpf) AS tamanho, COUNT(*) AS ocorrencias
        FROM {view}
        WHERE cnpj_cpf IS NOT NULL
        GROUP BY tipo_pessoa, LENGTH(cnpj_cpf)
        ORDER BY ocorrencias DESC
        FETCH FIRST {LIMITE_VALORES_POR_PERFIL} ROWS ONLY
    """
    sql_exemplos = f"""
        SELECT cnpj_cpf
        FROM {view}
        WHERE tipo_pessoa = :tipo_pessoa AND LENGTH(cnpj_cpf) = :tamanho
        FETCH FIRST {LIMITE_EXEMPLOS_CNPJ_POR_GRUPO} ROWS ONLY
    """
    valores: list[tuple[str, int]] = []
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql_grupos)
        grupos = cursor.fetchall()

        for tipo_pessoa, tamanho, ocorrencias in grupos:
            cursor.execute(sql_exemplos, tipo_pessoa=tipo_pessoa, tamanho=tamanho)
            ocorrencias_int = int(_comum.serializar(ocorrencias))
            for (documento,) in cursor.fetchall():
                valores.append((_mascarar_documento(str(documento)), ocorrencias_int))

    return PerfilCampo(modulo=_MODULO, view=view, campo="cnpj_cpf", valores=tuple(valores))


def _mascarar_documento(bruto: str) -> str:
    """Mantém só os 4 últimos caracteres visíveis, preservando o comprimento
    original (que é justamente o que se quer que a IA compare) — CPF/CNPJ é
    dado pessoal, não deve ir inteiro pro Ollama mesmo rodando local."""
    if len(bruto) <= 4:
        return bruto
    return "*" * (len(bruto) - 4) + bruto[-4:]


def _perfil_distinto(view: str, campo: str) -> PerfilCampo:
    sql = f"""
        SELECT {campo}, COUNT(*) AS ocorrencias
        FROM {view}
        WHERE {campo} IS NOT NULL
        GROUP BY {campo}
        ORDER BY ocorrencias DESC
        FETCH FIRST {LIMITE_VALORES_POR_PERFIL} ROWS ONLY
    """
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql)
        linhas = cursor.fetchall()

    valores = tuple((str(valor), int(_comum.serializar(ocorrencias))) for valor, ocorrencias in linhas)
    return PerfilCampo(modulo=_MODULO, view=view, campo=campo, valores=valores)
