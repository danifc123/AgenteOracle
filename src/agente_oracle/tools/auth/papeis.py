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

MODULOS_CONHECIDOS: tuple[str, ...] = ("financeiro",)


@dataclass(frozen=True)
class Papel:
    slug: str
    rotulo: str
    modulos: tuple[str, ...] = ()
    administrador: bool = False
    acesso_total: bool = False


PAPEIS_DISPONIVEIS: tuple[Papel, ...] = (
    Papel(slug="desenvolvedor", rotulo="Desenvolvedor", acesso_total=True, administrador=True),
    Papel(slug="financeiro_admin", rotulo="Administrador do Financeiro", modulos=("financeiro",), administrador=True),
    Papel(slug="financeiro", rotulo="Time do Financeiro", modulos=("financeiro",)),
)

_PAPEIS_POR_SLUG: dict[str, Papel] = {papel.slug: papel for papel in PAPEIS_DISPONIVEIS}


def _papeis_validos(papeis: list[str]) -> list[Papel]:
    return [_PAPEIS_POR_SLUG[slug] for slug in papeis if slug in _PAPEIS_POR_SLUG]


def tem_acesso_modulo(papeis: list[str], modulo: str) -> bool:
    return any(papel.acesso_total or modulo in papel.modulos for papel in _papeis_validos(papeis))


def eh_administrador(papeis: list[str]) -> bool:
    return any(papel.administrador for papel in _papeis_validos(papeis))


def modulos_liberados(papeis: list[str]) -> list[str]:
    validos = _papeis_validos(papeis)
    if any(papel.acesso_total for papel in validos):
        return list(MODULOS_CONHECIDOS)
    return sorted({modulo for papel in validos for modulo in papel.modulos})


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
