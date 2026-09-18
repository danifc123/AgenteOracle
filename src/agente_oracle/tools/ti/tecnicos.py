"""Roster de técnicos de TI — vem do cadastro de usuário do AgenteOracle
(tela "Usuários"), não mais de uma lista fixa em código. Quem cadastra um
usuário escolhe um técnico real do GLPI (`server/ti/tecnicos_glpi.py`
lista os candidatos), e a área (infra/sistemas/processos) é descoberta
sozinha a partir do grupo técnico manual da pessoa no GLPI
(`ClienteGLPIReal.buscar_area_do_tecnico`) — ver `usuarios_route` em
`server/auth/rotas.py`. `tools/auth/usuarios.py::listar_tecnicos_ti` é a
fonte do dado; este módulo só traduz pra `Tecnico` e escolhe por carga."""

from dataclasses import dataclass

from agente_oracle.tools.auth.usuarios import listar_tecnicos_ti
from agente_oracle.tools.ti.glpi import AreaChamado


class SemTecnicoNaArea(Exception):
    """Levantada por `escolher_tecnico` quando a área pedida não tem
    nenhum técnico cadastrado — sem isso, `min()` estourava `ValueError`
    cru (visto ao vivo: 500 sem mensagem útil em `chamado_verificar_route`).
    Quem chama decide como comunicar (rota HTTP devolve erro claro; o
    poller em background já isola falha por chamado e só loga)."""

    def __init__(self, area: AreaChamado):
        self.area = area
        super().__init__(f'Nenhum técnico cadastrado pra área "{area}".')


@dataclass(frozen=True)
class Tecnico:
    nome: str
    # Confirmado contra a instância real: é o `id` numérico do usuário no
    # GLPI (como string), o mesmo usado em `TeamMember.id` — ver
    # `ClienteGLPIReal.atribuir` em tools/ti/glpi.py.
    identificador: str
    area: AreaChamado
    # Login do AgenteOracle (não do GLPI) — usado só pra identificar "esse
    # técnico é o usuário logado" no painel de saúde do roster (mais
    # confiável que comparar por `nome`, que pode se repetir entre pessoas
    # diferentes — já vimos dois cadastros de "Daniel Faria" no sistema).
    usuario: str


def todos_os_tecnicos() -> tuple[Tecnico, ...]:
    """Consulta o Postgres a cada chamada, sem cache — aceitável pro
    volume atual (poucos chamados por rodada do poller), mesmo padrão de
    `server/auth/rotas.py::usuarios_route`, que já chama Postgres direto
    de dentro de rota `async def` sem thread pool. Vira gargalo só se o
    volume crescer muito; cacheia então, não antes. Público (não `_`) de
    propósito: `server/ti/chamados.py`/`webhook_glpi.py` usam pra montar
    a lista de identificadores em `carga_atual_por_tecnico` — precisam do
    roster fresco a cada chamada, não de uma cópia importada uma vez só
    na subida do servidor (`from ... import TECNICOS` congelaria o valor
    pra sempre, sem nunca ver técnico cadastrado depois)."""
    return tuple(
        Tecnico(
            nome=linha["nome"],
            identificador=linha["tecnico_glpi_id"],
            area=linha["area_ti"],
            usuario=linha["usuario"],
        )
        for linha in listar_tecnicos_ti()
    )


def escolher_tecnico(area: AreaChamado, cargas: dict[str, int]) -> Tecnico:
    """Escolhe o de menor carga dentro da área; empate resolvido pela
    ordem do roster (`listar_tecnicos_ti` ordena por quem cadastrou
    primeiro — determinístico, sem aleatoriedade) — `min()` já devolve o
    primeiro em caso de empate de chave. Levanta `SemTecnicoNaArea` (em vez
    de deixar `min()` estourar `ValueError` cru) quando a área não tem
    ninguém cadastrado — mais raro agora que técnico é obrigatório pra
    papel de TI, mas ainda possível (ex: único técnico de uma área foi
    apagado)."""
    tecnicos = tecnicos_da_area(area)
    if not tecnicos:
        raise SemTecnicoNaArea(area)
    return min(tecnicos, key=lambda tecnico: cargas.get(tecnico.identificador, 0))


def tecnicos_da_area(area: AreaChamado) -> tuple[Tecnico, ...]:
    return tuple(tecnico for tecnico in todos_os_tecnicos() if tecnico.area == area)
