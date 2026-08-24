"""Rota da Classificação Contábil — lógica de agrupamento/sugestão mora em
`agent/financeiro/classificacao_contabil.py`; este módulo só busca a
janela de `vw_lancamentos_contabeis` e monta a resposta HTTP, mesmo
espírito de `server/financeiro/despesas_suspeitas.py` (roda sob demanda,
nunca em background)."""

from datetime import date, timedelta

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.financeiro.classificacao_contabil import (
    LancamentoContabil,
    SugestaoClassificacao,
    construir_dicionario,
    mapa_conta_descricao,
    sugerir_classificacoes,
)
from agente_oracle.db.connection import get_connection
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in
from agente_oracle.tools.financeiro import classificacao_revisoes

_DIAS_HISTORICO = 365
_CONTA_NAO_DEFINIDA = "-1"
_RESULTADOS_VALIDOS = {"aceita", "corrigida"}


def _data(valor):
    return valor.date() if hasattr(valor, "date") else valor


def _buscar_lancamentos(filiais: list[str], desde: date) -> list[LancamentoContabil]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    sql = f"""
        SELECT documento, linha, conta, conta_descricao, historico, valor, data_movimentacao
        FROM vw_lancamentos_contabeis
        WHERE filial IN {clausula_filial}
          AND data_movimentacao >= :desde
    """
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, desde=desde, **binds_filial)
        linhas = cursor.fetchall()
    return [
        LancamentoContabil(
            documento=documento,
            linha=linha,
            conta=conta,
            conta_descricao=conta_descricao,
            historico=historico,
            valor=float(_comum.serializar(valor)),
            data_movimentacao=_data(data_movimentacao),
        )
        for (documento, linha, conta, conta_descricao, historico, valor, data_movimentacao) in linhas
    ]


def _sugestao_para_json(sugestao: SugestaoClassificacao) -> dict:
    return {
        "documento": sugestao.documento,
        "linha": sugestao.linha,
        "historico": sugestao.historico,
        "valor": sugestao.valor,
        "data_movimentacao": sugestao.data_movimentacao.isoformat(),
        "conta_sugerida": sugestao.conta_sugerida,
        "conta_descricao_sugerida": sugestao.conta_descricao_sugerida,
        "confianca_percentual": sugestao.confianca_percentual,
        "suporte_historico": sugestao.suporte_historico,
    }


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/classificacao-contabil", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def classificacao_contabil_route(request: Request, usuario: dict) -> Response:
        """Busca os lançamentos contábeis do último ano (classificados e
        não) e sugere conta pros sem classificação, por semelhança de
        histórico contra os já classificados — nunca inventa código de
        conta que não tenha precedente real (`agent/financeiro/
        classificacao_contabil.py`). Lançamento já revisado (aceito ou
        corrigido — ver `tools/financeiro/classificacao_revisoes.py`) não
        aparece mais aqui, mesmo continuando `-1` no Oracle (nunca
        escrevemos lá)."""
        filiais = _comum.filiais_da_query(request)
        if filiais is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        desde = date.today() - timedelta(days=_DIAS_HISTORICO)
        lancamentos = _buscar_lancamentos(filiais, desde)
        classificados = [lancamento for lancamento in lancamentos if lancamento.conta != _CONTA_NAO_DEFINIDA]

        revisadas = classificacao_revisoes.chaves_revisadas()
        nao_classificados = [
            lancamento
            for lancamento in lancamentos
            if lancamento.conta == _CONTA_NAO_DEFINIDA
            and (lancamento.documento, lancamento.linha) not in revisadas
        ]

        dicionario = construir_dicionario(classificados)
        descricoes = mapa_conta_descricao(classificados)
        sugestoes = sugerir_classificacoes(nao_classificados, dicionario, descricoes)

        _comum.registrar_acesso(usuario, "classificacao_contabil:analisar", len(sugestoes))
        return JSONResponse([_sugestao_para_json(sugestao) for sugestao in sugestoes], headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/classificacao-contabil/revisar", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def revisar_route(request: Request, usuario: dict) -> Response:
        """Marca uma sugestão como aceita (confirmada certa) ou corrigida
        (errada — `conta_correta` opcional, só se o usuário souber qual é a
        certa). Nunca escreve no Oracle/STAGE — só alimenta
        `resumo_precisao()`, a métrica real de acerto do sistema."""
        corpo = await request.json()
        documento = str(corpo.get("documento") or "").strip()
        linha = str(corpo.get("linha") or "").strip()
        conta_sugerida = str(corpo.get("conta_sugerida") or "").strip()
        resultado = str(corpo.get("resultado") or "").strip()
        conta_correta = str(corpo.get("conta_correta") or "").strip() or None

        if not documento or not linha or not conta_sugerida:
            return JSONResponse(
                {"erro": "Informe documento, linha e conta_sugerida."}, status_code=400, headers=CORS_HEADERS
            )
        if resultado not in _RESULTADOS_VALIDOS:
            return JSONResponse(
                {"erro": f"resultado precisa ser um de {sorted(_RESULTADOS_VALIDOS)}."},
                status_code=400,
                headers=CORS_HEADERS,
            )

        classificacao_revisoes.revisar(
            usuario["usuario"], documento, linha, conta_sugerida, resultado, conta_correta
        )
        _comum.registrar_acesso(usuario, "classificacao_contabil:revisar", 1)
        return JSONResponse({"ok": True}, headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/classificacao-contabil/precisao", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def precisao_route(request: Request, usuario: dict) -> Response:
        """Precisão medida de verdade (aceitas / total revisado) — ver
        `tools/financeiro/classificacao_revisoes.py::resumo_precisao`."""
        return JSONResponse(classificacao_revisoes.resumo_precisao(), headers=CORS_HEADERS)
