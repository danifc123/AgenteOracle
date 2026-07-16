"""Rotas REST dos relatórios fixos do módulo Financeiro. Cada relatório fica
em seu próprio arquivo (SQL + rotas), registrado aqui — a lista completa dos
relatórios previstos está em
frontend/grupoConceitoMCP/src/app/dadosRelatorios/modulos-financeiro.ts.

filiais.py e filtros_sql.py também moram aqui: são suporte compartilhado
entre os relatórios (lista de filiais pro seletor da tela, montagem de
cláusula IN), não relatórios em si.
"""

from agente_oracle.server.financeiro.relatorios import duplicata_mercantil, filiais, fluxo_caixa_realizado


def registrar(mcp) -> None:
    filiais.registrar(mcp)
    fluxo_caixa_realizado.registrar(mcp)
    duplicata_mercantil.registrar(mcp)
