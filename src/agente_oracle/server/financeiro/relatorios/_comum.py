"""Utilitários compartilhados entre os relatórios fixos de `relatorios/*.py` —
extraído porque `serializar`, `filiais_da_query` e `parametros_opcionais`
eram copiados byte-a-byte em praticamente todo arquivo do módulo."""

from decimal import Decimal

from starlette.requests import Request


def filiais_da_query(request: Request) -> list[str] | None:
    """Lê o parâmetro 'filial' (obrigatório, aceita múltiplas separadas por
    vírgula). Devolve None quando nenhuma filial foi informada."""
    bruto = request.query_params.get("filial", "").strip()
    filiais = [item.strip() for item in bruto.split(",") if item.strip()]
    return filiais or None


def parametros_opcionais(request: Request, campos: tuple[str, ...]) -> dict[str, str]:
    return {chave: request.query_params.get(chave, "").strip() for chave in campos}


def serializar(valor):
    """Converte Decimal (não serializável em JSON puro) pra float; passa o resto direto."""
    return float(valor) if isinstance(valor, Decimal) else valor
