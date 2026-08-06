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
física e 14 pra jurídica)."""

from agente_oracle.agent.auditoria.perfil_campo import PerfilCampo
from agente_oracle.db.connection import get_connection
from agente_oracle.server.financeiro.relatorios import _comum

_MODULO = "financeiro"

# `filial` existe (e deveria seguir o mesmo padrão de numeração) em todas
# essas views; `estado`/`tipo_pessoa`/`cnpj_cpf` só existem no cadastro.
_VIEWS_COM_FILIAL = ("vw_titulos_pagar", "vw_titulos_receber", "vw_faturamento", "vw_clientes", "vw_fornecedores")
_VIEWS_CADASTRO = ("vw_clientes", "vw_fornecedores")

# Protege o num_ctx do Ollama (16384, mesma constante usada no resto do
# projeto) de estourar se um campo que devia ser baixa cardinalidade não for,
# na prática, por dado sujo.
LIMITE_VALORES_POR_PERFIL = 50
LIMITE_EXEMPLOS_CNPJ_POR_GRUPO = 3


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


def construir_perfis_financeiro() -> list[PerfilCampo]:
    perfis = [_perfil_distinto(view, "filial") for view in _VIEWS_COM_FILIAL]
    for view in _VIEWS_CADASTRO:
        perfis.append(_perfil_distinto(view, "estado"))
        perfis.append(_perfil_distinto(view, "tipo_pessoa"))
        perfis.append(_perfil_cnpj_cpf(view))
    return perfis
