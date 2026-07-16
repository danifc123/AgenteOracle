"""Rotas REST dos relatórios fixos do módulo Financeiro. Cada relatório fica
em seu próprio arquivo (SQL + rotas), registrado aqui — a lista completa dos
relatórios previstos está em
frontend/grupoConceitoMCP/src/app/dadosRelatorios/modulos-financeiro.ts.
"""

from agente_oracle.server.financeiro.relatorios import duplicata_mercantil, fluxo_caixa_realizado


def registrar(mcp) -> None:
    fluxo_caixa_realizado.registrar(mcp)
    duplicata_mercantil.registrar(mcp)
