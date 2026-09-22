"""Roster de técnicos de TI — vem do cadastro de usuário do AgenteOracle
(tela "Usuários"), não mais de uma lista fixa em código. Quem cadastra um
usuário escolhe um técnico real do GLPI (`server/ti/tecnicos_glpi.py`
lista os candidatos), e a área (infra/sistemas/processos) é descoberta
sozinha a partir do grupo técnico manual da pessoa no GLPI
(`ClienteGLPIReal.buscar_area_do_tecnico`) — ver `usuarios_route` em
`server/auth/rotas.py`. `tools/auth/usuarios.py::listar_tecnicos_ti` é a
fonte do dado; este módulo só traduz pra `Tecnico` e escolhe por carga.

`escolher_tecnico` também dá prioridade a um técnico citado pelo nome no
próprio texto do chamado (ex: "abrir pro Pablo") — sempre dentro da área
já resolvida pela categoria, nunca decidindo área sozinho. Citação
ambígua (nenhum nome bate, ou mais de um) cai no critério de sempre
(menor carga), sem tentar adivinhar."""

import re
import unicodedata
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


def escolher_tecnico(area: AreaChamado, cargas: dict[str, int], texto_chamado: str = "") -> Tecnico:
    """Escolhe o de menor carga dentro da área; empate resolvido pela
    ordem do roster (`listar_tecnicos_ti` ordena por quem cadastrou
    primeiro — determinístico, sem aleatoriedade) — `min()` já devolve o
    primeiro em caso de empate de chave. Levanta `SemTecnicoNaArea` (em vez
    de deixar `min()` estourar `ValueError` cru) quando a área não tem
    ninguém cadastrado — mais raro agora que técnico é obrigatório pra
    papel de TI, mas ainda possível (ex: único técnico de uma área foi
    apagado).

    `texto_chamado` (título + descrição, opcional) tem prioridade sobre a
    carga quando cita um único técnico dessa área pelo nome — ver
    `_tecnico_citado_por_nome`."""
    tecnicos = tecnicos_da_area(area)
    if not tecnicos:
        raise SemTecnicoNaArea(area)
    citado = _tecnico_citado_por_nome(texto_chamado, tecnicos) if texto_chamado else None
    if citado:
        return citado
    return min(tecnicos, key=lambda tecnico: cargas.get(tecnico.identificador, 0))


def tecnicos_da_area(area: AreaChamado) -> tuple[Tecnico, ...]:
    return tuple(tecnico for tecnico in todos_os_tecnicos() if tecnico.area == area)


def _tecnico_citado_por_nome(texto: str, tecnicos: tuple[Tecnico, ...]) -> Tecnico | None:
    """Compara o primeiro nome de cada técnico contra o texto — palavra
    inteira, sem acento, sem diferenciar maiúscula/minúscula (pra "Pablo"
    não casar com "Pablosistema" nem depender de como foi digitado). Mais
    de um nome citado é ambíguo de propósito: melhor cair no critério de
    carga do que arriscar escolher o técnico errado."""
    texto_normalizado = _sem_acento(texto)
    citados = [
        tecnico
        for tecnico in tecnicos
        if re.search(rf"\b{re.escape(_sem_acento(tecnico.nome.split()[0]))}\b", texto_normalizado)
    ]
    return citados[0] if len(citados) == 1 else None


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(caractere for caractere in decomposto if not unicodedata.combining(caractere)).lower()
