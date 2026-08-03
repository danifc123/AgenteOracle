"""Estrutura de dado genérica que alimenta a análise de auditoria
(`agent/auditoria/analise.py`) — não sabe nada de SQL nem de nenhum módulo
específico. Cada módulo (Financeiro, e futuramente outros) monta sua própria
lista de `PerfilCampo` a partir das views que conhece (ver
`agent/financeiro/auditoria.py` como referência de implementação)."""

from dataclasses import dataclass


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
