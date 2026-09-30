"""Catálogo dos indicadores (widgets) de RH disponíveis na Home unificada
(`server/home/dashboard.py`) — mesmo espírito de
`server/ti/dashboard_widgets.py`: só o dado, sem rota nem lógica de
visibilidade.

RH não tem indicador de dado hoje (nenhuma métrica candidata definida) —
só os ATALHOS de navegação que antes ficavam fixos na Home do RH, agora
widget igual qualquer outro, sem dado pra buscar (ver `WidgetAtalho` no
frontend, `componentes/widget-atalho/`). Nenhum widget aqui exige
`desenvolvedor`."""

from typing import NamedTuple

from agente_oracle.server.ti.dashboard_widgets import Tamanho


class DefinicaoWidget(NamedTuple):
    titulo: str
    exige_dev: bool
    tamanho_padrao: Tamanho
    exige_administrador: bool = False


CATALOGO: dict[str, DefinicaoWidget] = {
    "analise_candidato": DefinicaoWidget(
        titulo="Análise de Candidato", exige_dev=False, tamanho_padrao="pequeno"
    ),
    "repescagem": DefinicaoWidget(titulo="Repescagem", exige_dev=False, tamanho_padrao="pequeno"),
    "colaboradores": DefinicaoWidget(titulo="Colaboradores", exige_dev=False, tamanho_padrao="pequeno"),
}
