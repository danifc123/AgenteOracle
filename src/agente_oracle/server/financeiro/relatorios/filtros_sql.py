"""Utilitário compartilhado entre os relatórios do Financeiro: monta uma
cláusula "IN (...)" e os binds correspondentes a partir de uma lista de
valores (ex: as filiais escolhidas pelo usuário na tela, que agora aceita
seleção múltipla)."""


def clausula_in(nome_base: str, valores: list[str]) -> tuple[str, dict[str, str]]:
    """Monta uma cláusula "(:nome_0, :nome_1, ...)" e o dict de binds
    correspondente. Use assim: `f"coluna IN {clausula}"`."""
    binds = {f"{nome_base}_{indice}": valor for indice, valor in enumerate(valores)}
    marcadores = ", ".join(f":{chave}" for chave in binds)
    return f"({marcadores})", binds
