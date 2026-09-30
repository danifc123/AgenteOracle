"""Catálogo dos indicadores (widgets) de Financeiro disponíveis na Home
unificada (`server/home/dashboard.py`) — mesmo espírito de
`server/ti/dashboard_widgets.py`: só o dado, sem rota nem lógica de
visibilidade.

`faturamento_total`/`saldo_projetado` não têm rota de dado própria: o
componente do widget consome direto as rotas de previsão que já existem
(`/api/financeiro/previsao/vendas`, `/api/financeiro/previsao/fluxo-caixa`
— `server/financeiro/previsao.py`, NDJSON em streaming, `gerarPrevisaoStream`
no frontend), pedindo todas as filiais liberadas pro usuário
(`/api/financeiro/filiais`, que já exclui as bloqueadas — ver
`server/financeiro/relatorios/filiais.py`). Os demais são os ATALHOS de
navegação que antes ficavam fixos na Home do Financeiro — viraram widget
igual qualquer outro, sem dado pra buscar (ver `WidgetAtalho` no frontend,
`componentes/widget-atalho/`). Nenhum widget aqui exige `desenvolvedor` —
é conteúdo normal de qualquer um do módulo Financeiro."""

from typing import NamedTuple

from agente_oracle.server.ti.dashboard_widgets import Tamanho


class DefinicaoWidget(NamedTuple):
    titulo: str
    exige_dev: bool
    tamanho_padrao: Tamanho
    exige_administrador: bool = False


CATALOGO: dict[str, DefinicaoWidget] = {
    "faturamento_total": DefinicaoWidget(
        titulo="Faturamento total (últimos 12 meses)", exige_dev=False, tamanho_padrao="pequeno"
    ),
    "saldo_projetado": DefinicaoWidget(
        titulo="Saldo projetado (a receber - a pagar)", exige_dev=False, tamanho_padrao="pequeno"
    ),
    "modulos_financeiros": DefinicaoWidget(
        titulo="Módulos financeiros", exige_dev=False, tamanho_padrao="pequeno"
    ),
    "criar_relatorio": DefinicaoWidget(titulo="Criar relatório", exige_dev=False, tamanho_padrao="pequeno"),
    "assistente_ia": DefinicaoWidget(titulo="Assistente IA", exige_dev=False, tamanho_padrao="pequeno"),
    "historico_relatorios": DefinicaoWidget(
        titulo="Histórico de relatórios", exige_dev=False, tamanho_padrao="pequeno"
    ),
}
