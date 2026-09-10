"""Roster de técnicos de TI, em código (não banco) — muda raro o bastante
pra "editar código, dar deploy" ser aceitável, e não existe tela de admin
no projeto pra editar isso com segurança. Se um dia existir uma tela de
admin de TI, migrar pra uma tabela Postgres (mesmo padrão `CREATE TABLE IF
NOT EXISTS` já usado no projeto) é o caminho natural.

Roster reduzido de propósito pra fase de teste em homologação: só 1
técnico por área (Pablo/infra, Denner/sistemas, Suellen/processos),
escolhidos pelo Daniel entre os membros reais dos grupos GLPI
"Infraestrutura de TI"/"Sistemas"/"Processos e Projetos". Com só 1 por
área, `escolher_tecnico` sempre devolve o mesmo — é o comportamento
esperado nesta fase, não um bug. Expandir pra mais gente por área é só
adicionar linha na tupla abaixo."""

from dataclasses import dataclass

from agente_oracle.tools.ti.glpi import AreaChamado


@dataclass(frozen=True)
class Tecnico:
    nome: str
    # Confirmado contra a instância real: é o `id` numérico do usuário no
    # GLPI (como string), o mesmo usado em `TeamMember.id` — ver
    # `ClienteGLPIReal.atribuir` em tools/ti/glpi.py.
    identificador: str
    area: AreaChamado


TECNICOS: tuple[Tecnico, ...] = (
    Tecnico("Pablo Pires de Godoi Silva", "7", "infra"),
    Tecnico("Denner Mendonça dos Santos", "8", "sistemas"),
    Tecnico("Suellen Moraes Silva", "278", "processos"),
)


def escolher_tecnico(area: AreaChamado, cargas: dict[str, int]) -> Tecnico:
    """Escolhe o de menor carga dentro da área; empate resolvido pela ordem
    fixa em `TECNICOS` (determinístico, sem aleatoriedade) — `min()` já
    devolve o primeiro em caso de empate de chave."""
    return min(tecnicos_da_area(area), key=lambda tecnico: cargas.get(tecnico.identificador, 0))


def tecnicos_da_area(area: AreaChamado) -> tuple[Tecnico, ...]:
    return tuple(tecnico for tecnico in TECNICOS if tecnico.area == area)
