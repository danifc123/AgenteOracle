"""Papéis de usuário — fonte única de verdade do que cada um libera,
compartilhada entre as rotas de autenticação (checagem de acesso) e a tela de
administração de usuários (lista de papéis disponíveis pra atribuir). Mesmo
espírito do `RelacionamentoView` em `agent/financeiro/schema.py`: declarar o
dado estruturado aqui, e derivar o resto (nunca espalhar `if papel == "x"`
pelo código).

Adicionar um módulo novo (RH, Compras...) é só incluir o slug em
`MODULOS_CONHECIDOS` e apontar `modulos=(...)` no(s) papel(is) que devem
acessá-lo — `desenvolvedor` (que tem `acesso_total`) ganha o módulo novo
automaticamente, sem precisar editar nada aqui.
"""

from dataclasses import dataclass

MODULOS_CONHECIDOS: tuple[str, ...] = ("financeiro", "estoque")

# Sigla curta usada em nomes de arquivo exportado (ex:
# `planilhas_combinadas_FIN.xlsx`), pra quem baixa saber de qual time veio.
# Módulo novo sem entrada aqui ainda funciona — `sigla_modulo` cai num
# fallback derivado do nome — mas vale adicionar a sigla "oficial" junto de
# `MODULOS_CONHECIDOS` quando um módulo novo (RH, Compras...) for criado.
SIGLAS_MODULO: dict[str, str] = {
    "financeiro": "FIN",
    "estoque": "EST",
}


@dataclass(frozen=True)
class Papel:
    slug: str
    rotulo: str
    modulos: tuple[str, ...] = ()
    administrador: bool = False
    acesso_total: bool = False


# NOTA DE SEGURANÇA (revisão de 2026): `desenvolvedor` concentra bastante
# poder — `acesso_total` dá acesso automático a TODO módulo (presente e
# futuro, sem precisar editar nada aqui) e `administrador` dá acesso a toda
# rota administrativa (gerenciar usuário, desbloquear conta, ver a trilha de
# auditoria em `eventos_seguranca`). Hoje isso é aceitável (time pequeno,
# `desenvolvedor` = quem já tem acesso ao código-fonte e ao banco mesmo). Se
# o time crescer, vale considerar separar "acesso de dados" (ver
# Financeiro/Estoque) de "administração do sistema" (gerenciar usuário,
# desbloquear conta) em papéis distintos, em vez de um papel só cobrindo os
# dois. Não é um bug — é uma decisão de design que vale reavaliar mais pra
# frente, não uma ação pendente.
PAPEIS_DISPONIVEIS: tuple[Papel, ...] = (
    Papel(slug="desenvolvedor", rotulo="Desenvolvedor", acesso_total=True, administrador=True),
    Papel(slug="financeiro_admin", rotulo="Administrador do Financeiro", modulos=("financeiro",), administrador=True),
    Papel(slug="financeiro", rotulo="Time do Financeiro", modulos=("financeiro",)),
    Papel(slug="estoque_admin", rotulo="Administrador do Estoque", modulos=("estoque",), administrador=True),
    Papel(slug="estoque", rotulo="Time do Estoque", modulos=("estoque",)),
)

_PAPEIS_POR_SLUG: dict[str, Papel] = {papel.slug: papel for papel in PAPEIS_DISPONIVEIS}


def _papeis_validos(papeis: list[str]) -> list[Papel]:
    return [_PAPEIS_POR_SLUG[slug] for slug in papeis if slug in _PAPEIS_POR_SLUG]


def tem_acesso_modulo(papeis: list[str], modulo: str) -> bool:
    return any(papel.acesso_total or modulo in papel.modulos for papel in _papeis_validos(papeis))


def eh_administrador(papeis: list[str]) -> bool:
    return any(papel.administrador for papel in _papeis_validos(papeis))


def eh_desenvolvedor(papeis: list[str]) -> bool:
    """Diferente de `eh_administrador` (verdadeiro pra qualquer papel
    administrador, ex: `financeiro_admin`), aqui é só o papel `desenvolvedor`
    especificamente — usado por funcionalidades de teste/depuração (ex:
    ativar/desativar achado de auditoria) que não devem aparecer nem pra
    administradores de módulo comuns."""
    return any(papel.slug == "desenvolvedor" for papel in _papeis_validos(papeis))


def modulos_liberados(papeis: list[str]) -> list[str]:
    validos = _papeis_validos(papeis)
    if any(papel.acesso_total for papel in validos):
        return list(MODULOS_CONHECIDOS)
    return sorted({modulo for papel in validos for modulo in papel.modulos})


def sigla_modulo(modulo: str) -> str:
    """Sigla curta de um módulo pra usar em nome de arquivo exportado.
    Sem entrada em `SIGLAS_MODULO`, cai num fallback com as 3 primeiras
    letras do próprio nome — não trava a exportação por módulo novo sem
    sigla cadastrada."""
    return SIGLAS_MODULO.get(modulo, modulo[:3].upper())


def sigla_usuario(papeis_usuario: list[str]) -> str:
    """Sigla que identifica de qual time veio um arquivo exportado pelo
    usuário logado. Desenvolvedor (acesso a todos os módulos) usa `DEV` em
    vez da lista inteira; usuário sem nenhum módulo liberado (não deveria
    acontecer pra quem já passou por `exigir_usuario`) devolve string vazia."""
    if eh_desenvolvedor(papeis_usuario):
        return "DEV"

    modulos = modulos_liberados(papeis_usuario)
    return sigla_modulo(modulos[0]) if modulos else ""


def pode_atribuir_papel(papeis_de_quem_cria: list[str], papel_alvo: str) -> bool:
    """Só quem tem um papel com `acesso_total` pode atribuir outro papel com
    `acesso_total` — evita que um administrador do financeiro promova alguém
    a desenvolvedor. Papéis desconhecidos nunca podem ser atribuídos."""
    alvo = _PAPEIS_POR_SLUG.get(papel_alvo)
    if alvo is None:
        return False
    if not alvo.acesso_total:
        return True
    return any(papel.acesso_total for papel in _papeis_validos(papeis_de_quem_cria))
