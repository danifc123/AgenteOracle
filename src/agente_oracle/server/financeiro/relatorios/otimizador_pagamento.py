"""RELATÓRIO: Otimizador de Fluxo de Caixa Preditivo — não é tradução de
relatório legado (sem código FINRxxx equivalente), item novo da planilha
de demandas de IA do Financeiro ("Contas a Pagar e Fluxo de Caixa").

100% cálculo sobre o histórico real de pagamento
(`agent/financeiro/otimizador_pagamento.py`), sem IA — mesmo espírito de
`desvio_margem.py`/`projecoes.py` ("número não pode depender do Ollama
estar no ar"). Usa a view curada `vw_titulos_pagar` (`agent/financeiro/
schema.py`), que ganhou `valor_desconto`/`valor_multa`/`valor_juros`/
`data_baixa` nesta rodada."""

from datetime import date, timedelta

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.financeiro.otimizador_pagamento import (
    RecomendacaoPagamento,
    TituloPagarAberto,
    TituloPagarLiquidado,
    perfil_por_fornecedor,
    recomendar_pagamentos,
)
from agente_oracle.db.connection import get_connection
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

_DIAS_HISTORICO = 365

_COLUNAS = (
    "fornecedor_codigo",
    "fornecedor_nome",
    "documento",
    "valor_original",
    "data_vencimento",
    "data_recomendada",
    "economia_estimada",
    "motivo",
)


def _data(valor):
    return valor.date() if hasattr(valor, "date") else valor


def _buscar_liquidados(filiais: list[str], desde: date) -> list[TituloPagarLiquidado]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    sql = f"""
        SELECT fornecedor_codigo, fornecedor_nome, valor_original, data_vencimento,
               data_baixa, valor_desconto, valor_multa, valor_juros
        FROM vw_titulos_pagar
        WHERE filial IN {clausula_filial}
          AND data_baixa IS NOT NULL
          AND data_baixa >= :desde
    """
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, desde=desde, **binds_filial)
        linhas = cursor.fetchall()
    return [
        TituloPagarLiquidado(
            fornecedor_codigo=fornecedor_codigo,
            fornecedor_nome=fornecedor_nome,
            valor_original=float(_comum.serializar(valor_original)),
            data_vencimento=_data(data_vencimento),
            data_baixa=_data(data_baixa),
            valor_desconto=float(_comum.serializar(valor_desconto) or 0),
            valor_multa=float(_comum.serializar(valor_multa) or 0),
            valor_juros=float(_comum.serializar(valor_juros) or 0),
        )
        for (
            fornecedor_codigo,
            fornecedor_nome,
            valor_original,
            data_vencimento,
            data_baixa,
            valor_desconto,
            valor_multa,
            valor_juros,
        ) in linhas
    ]


def _buscar_abertos(filiais: list[str]) -> list[TituloPagarAberto]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    sql = f"""
        SELECT fornecedor_codigo, fornecedor_nome, prefixo, numero, parcela,
               valor_original, data_vencimento
        FROM vw_titulos_pagar
        WHERE filial IN {clausula_filial} AND saldo_aberto > 0
    """
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, **binds_filial)
        linhas = cursor.fetchall()
    return [
        TituloPagarAberto(
            fornecedor_codigo=fornecedor_codigo,
            fornecedor_nome=fornecedor_nome,
            prefixo=prefixo,
            numero=numero,
            parcela=parcela,
            valor_original=float(_comum.serializar(valor_original)),
            data_vencimento=_data(data_vencimento),
        )
        for (
            fornecedor_codigo,
            fornecedor_nome,
            prefixo,
            numero,
            parcela,
            valor_original,
            data_vencimento,
        ) in linhas
    ]


def _buscar_recomendacoes(filiais: list[str]) -> list[RecomendacaoPagamento]:
    desde = date.today() - timedelta(days=_DIAS_HISTORICO)
    perfis = perfil_por_fornecedor(_buscar_liquidados(filiais, desde))
    return recomendar_pagamentos(_buscar_abertos(filiais), perfis)


def _recomendacao_para_linha(recomendacao: RecomendacaoPagamento) -> tuple:
    return (
        recomendacao.fornecedor_codigo,
        recomendacao.fornecedor_nome,
        recomendacao.documento,
        recomendacao.valor_original,
        recomendacao.data_vencimento.isoformat(),
        recomendacao.data_recomendada.isoformat(),
        recomendacao.economia_estimada,
        recomendacao.motivo,
    )


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/otimizador-pagamento/exportar", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def exportar_otimizador_pagamento_route(request: Request, usuario: dict) -> Response:
        """RELATÓRIO: Otimizador de Fluxo de Caixa Preditivo — exportação em Excel."""
        filiais = _comum.filiais_da_query(request)
        if filiais is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        recomendacoes = _buscar_recomendacoes(filiais)
        _comum.registrar_acesso(usuario, "otimizador_pagamento:exportar", len(recomendacoes))
        linhas = [_recomendacao_para_linha(recomendacao) for recomendacao in recomendacoes]
        conteudo_xlsx = gerar_xlsx(_COLUNAS, linhas, titulo="Otimizador de Pagamento")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="otimizador_pagamento.xlsx"',
                **CORS_HEADERS,
            },
        )

    @mcp.custom_route("/api/financeiro/otimizador-pagamento", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def listar_otimizador_pagamento_route(request: Request, usuario: dict) -> JSONResponse:
        """RELATÓRIO: Otimizador de Fluxo de Caixa Preditivo — endpoint JSON usado pela tela."""
        filiais = _comum.filiais_da_query(request)
        if filiais is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        recomendacoes = _buscar_recomendacoes(filiais)
        _comum.registrar_acesso(usuario, "otimizador_pagamento:listar", len(recomendacoes))
        dados = [
            dict(zip(_COLUNAS, _recomendacao_para_linha(recomendacao), strict=True))
            for recomendacao in recomendacoes
        ]
        return JSONResponse(dados, headers=CORS_HEADERS)
