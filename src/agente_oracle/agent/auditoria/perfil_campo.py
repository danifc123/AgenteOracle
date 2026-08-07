"""Estrutura de dado genérica que alimenta a análise de auditoria
(`agent/auditoria/analise.py`) — não sabe nada de SQL nem de nenhum módulo
específico. Cada módulo (Financeiro, e futuramente outros) monta sua própria
lista de `PerfilCampo` a partir das views que conhece (ver
`agent/financeiro/auditoria.py` como referência de implementação)."""

import re
from dataclasses import dataclass

# Guard-rail de segurança: nenhum campo com nome de credencial/hash pode ser
# auditado pela IA, mesmo que uma view futura venha a expor um assim — o
# sistema será usado com dado real de empresa, não só o schema de teste atual
# (que não tem nenhum campo desses). CPF/CNPJ tem tratamento próprio
# (mascarado em `agent/financeiro/auditoria.py::_mascarar_documento`) e não
# entra nesse filtro.
_PADRAO_CAMPO_SENSIVEL = re.compile(
    r"(senha|password|passwd|hash|token|secret|segredo|chave|api_key|pin|cvv)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PerfilCampo:
    """Um resumo (não os dados brutos) de um campo de uma view: os valores
    distintos mais frequentes (ou exemplos, para campos de alta
    cardinalidade), cada um com sua contagem de ocorrências — é isso que a IA
    recebe para decidir o que parece fora do padrão em `campo`."""

    modulo: str
    view: str
    campo: str
    valores: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if not campo_seguro_para_auditoria(self.campo):
            raise ValueError(
                f"Campo '{self.campo}' parece ser credencial/hash e não pode ser auditado pela IA."
            )


def campo_seguro_para_auditoria(nome_campo: str) -> bool:
    """`False` se o nome do campo soa como credencial ou valor criptografado
    — não deve ser enviado ao LLM."""
    return not _PADRAO_CAMPO_SENSIVEL.search(nome_campo)
