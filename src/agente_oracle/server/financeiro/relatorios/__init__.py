"""Rotas REST dos relatórios fixos do módulo Financeiro. Cada relatório fica
em seu próprio arquivo (SQL + rotas), registrado aqui — a lista completa dos
relatórios previstos está em
frontend/grupoConceitoMCP/src/app/dadosRelatorios/modulos-financeiro.ts.

filiais.py, filtros_sql.py e cadastros.py também moram aqui: são suporte
compartilhado entre os relatórios (lista de filiais/clientes/vendedores pro
seletor da tela, montagem de cláusula IN), não relatórios em si.
"""

from agente_oracle.server.financeiro.relatorios import (
    baixa_produtos,
    cadastros,
    duplicata_mercantil,
    filiais,
    fluxo_caixa_realizado,
    posicao_titulos,
    posicao_titulos_pagar,
    relacao_baixas,
)


def registrar(mcp) -> None:
    filiais.registrar(mcp)
    cadastros.registrar(mcp)
    fluxo_caixa_realizado.registrar(mcp)
    duplicata_mercantil.registrar(mcp)
    baixa_produtos.registrar(mcp)
    posicao_titulos.registrar(mcp)
    posicao_titulos_pagar.registrar(mcp)
    relacao_baixas.registrar(mcp)
