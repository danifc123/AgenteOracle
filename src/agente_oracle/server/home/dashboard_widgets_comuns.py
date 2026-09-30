"""Catálogo dos widgets COMUNS da Home unificada (`server/home/dashboard.py`)
— não pertencem a nenhum módulo (`papeis.MODULOS_CONHECIDOS`), então ficam
disponíveis pra qualquer usuário autenticado, independente de papel (o
namespace de id deles é `"comum:<id>"`, não o de um módulo real).

`usuarios` é a exceção: não é gate de módulo, mas ainda exige
`papeis.eh_administrador` (qualquer admin de qualquer módulo, não só quem
tem acesso a um módulo específico — mesmo critério de `adminGuard` no
frontend pra rota `/usuarios`)."""

from typing import NamedTuple

from agente_oracle.server.ti.dashboard_widgets import Tamanho


class DefinicaoWidget(NamedTuple):
    titulo: str
    exige_dev: bool
    tamanho_padrao: Tamanho
    exige_administrador: bool = False


CATALOGO: dict[str, DefinicaoWidget] = {
    "central_suporte": DefinicaoWidget(titulo="Central de suporte", exige_dev=False, tamanho_padrao="pequeno"),
    "usuarios": DefinicaoWidget(
        titulo="Usuários", exige_dev=False, tamanho_padrao="pequeno", exige_administrador=True
    ),
}
