"""Catálogo dos indicadores (widgets) de TI disponíveis na Home unificada
(`server/home/dashboard.py`) — só o dado, sem rota nem lógica de
visibilidade (isso é responsabilidade de quem monta o catálogo unificado).
Extraído do antigo `server/ti/dashboard.py` (rota própria `/api/ti/dashboard`,
aposentada em favor da Home única — ver `server/home/dashboard.py`)."""

from typing import Literal, NamedTuple

Tamanho = Literal["pequeno", "grande"]
TAMANHOS_VALIDOS: set[str] = {"pequeno", "grande"}


class DefinicaoWidget(NamedTuple):
    titulo: str
    exige_dev: bool
    tamanho_padrao: Tamanho
    # Só widget do tipo atalho (`comum:usuarios`, ver
    # `server/home/dashboard_widgets_comuns.py`) usa isso hoje — default
    # `False` pra não obrigar todo `DefinicaoWidget(...)` já escrito a
    # passar o campo.
    exige_administrador: bool = False


# id (sem namespace — quem monta o catálogo unificado prefixa com "ti:") ->
# definição. Mesmo catálogo de sempre, só sem `_LAYOUT_PADRAO`: a Home
# unificada começa em branco de propósito, não tem mais "layout de quem
# nunca personalizou nada" fixo (ver docstring de `server/home/dashboard.py`).
#
# Além dos indicadores de dado (`chamados_*`/`ia_*`/`seguranca_*`), o
# catálogo também inclui os ATALHOS de navegação que antes ficavam fixos na
# Home do TI (`seguranca`, `auditoria_chamados`) — viraram widget igual
# qualquer outro, só que sem dado pra buscar (ver `WidgetAtalho` no
# frontend, `componentes/widget-atalho/`).
CATALOGO: dict[str, DefinicaoWidget] = {
    "chamados_total": DefinicaoWidget(titulo="Chamados em aberto", exige_dev=False, tamanho_padrao="pequeno"),
    "chamados_por_status": DefinicaoWidget(
        titulo="Chamados por status", exige_dev=False, tamanho_padrao="grande"
    ),
    "ia_tokens_hoje": DefinicaoWidget(titulo="Tokens de IA hoje", exige_dev=True, tamanho_padrao="pequeno"),
    "ia_chamados_avaliados": DefinicaoWidget(
        titulo="Chamados avaliados pela IA", exige_dev=True, tamanho_padrao="pequeno"
    ),
    "ia_chamados_escalados": DefinicaoWidget(
        titulo="Chamados escalados pela IA", exige_dev=True, tamanho_padrao="pequeno"
    ),
    "ia_categoria_nao_corrigida": DefinicaoWidget(
        titulo="Categoria não corrigida automaticamente", exige_dev=True, tamanho_padrao="pequeno"
    ),
    # Achados ativos de `historico_seguranca` (login/acesso suspeito no
    # Protheus e no próprio AgenteOracle, ver `agent/ti/deteccao_seguranca.py`)
    # — reaproveita `GET /api/ti/seguranca/historico`, que já devolve só os
    # ativos pra quem não é desenvolvedor; não precisa de rota nova.
    "seguranca_achados_ativos": DefinicaoWidget(
        titulo="Achados de segurança ativos", exige_dev=False, tamanho_padrao="pequeno"
    ),
    "seguranca": DefinicaoWidget(titulo="Segurança de TI", exige_dev=False, tamanho_padrao="pequeno"),
    "auditoria_chamados": DefinicaoWidget(
        titulo="Auditoria de Chamados", exige_dev=False, tamanho_padrao="pequeno"
    ),
}
