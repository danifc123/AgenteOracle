"""RELATÓRIO: Orçamento Base Zero Automatizado — não é tradução de
relatório legado (sem código FINRxxx equivalente), item novo da planilha
de demandas de IA do Financeiro (FP&A).

"Base zero" aqui significa literalmente isso: não existe orçamento
aprovado anterior em lugar nenhum do sistema pra comparar (mapeado antes
de escrever este arquivo — nem tabela, nem view, nem menção a Excel
externo em código) — a sugestão de orçamento nasce inteira do histórico
real de despesa por categoria (natureza financeira) dos últimos
`_MESES_HISTORICO` meses, não de um orçamento anterior ajustado.

Mesmo espírito de `agent/financeiro/projecoes.py` ("100% cálculo
estatístico, sem IA"): reaproveita `projetar_tendencia_linear` direto
(sem duplicar a matemática de regressão), aplicada por categoria em vez
de um total único — número não depende do Ollama estar no ar."""

from datetime import date

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.financeiro.projecoes import projetar_tendencia_linear
from agente_oracle.db.connection import get_connection
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

_MESES_HISTORICO = 12
_MESES_PROJECAO = 12

_COLUNAS = (
    "natureza_codigo",
    "natureza_descricao",
    "media_historica_mensal",
    "total_historico_12_meses",
    "orcamento_sugerido_proximo_ano",
    "variacao_percentual",
)

_QUERY = """
    SELECT
        natureza_codigo,
        natureza_descricao,
        TO_CHAR(data_emissao, 'YYYY-MM') AS mes,
        SUM(valor_original) AS total
    FROM vw_titulos_pagar
    WHERE filial IN __FILIAL_IN__
      AND TO_CHAR(data_emissao, 'YYYY-MM') >= :mes_inicio
    GROUP BY natureza_codigo, natureza_descricao, TO_CHAR(data_emissao, 'YYYY-MM')
"""


def _janela_meses_historico(quantidade: int) -> list[str]:
    """Os `quantidade` rótulos "YYYY-MM" mais recentes, em ordem crescente,
    terminando no mês atual (mesma lógica duplicada em outras rotas do
    Financeiro — cada uma é self-contida, sem módulo de suporte
    compartilhado pra isso)."""
    mes_atual = date.today().strftime("%Y-%m")
    meses = [mes_atual, *[_mes_menos(mes_atual, passo) for passo in range(1, quantidade)]]
    meses.reverse()
    return meses


def _mes_menos(mes_referencia: str, quantidade: int) -> str:
    ano, mes = (int(parte) for parte in mes_referencia.split("-"))
    total_meses = ano * 12 + (mes - 1) - quantidade
    ano_resultado, mes_resultado = divmod(total_meses, 12)
    return f"{ano_resultado:04d}-{mes_resultado + 1:02d}"


def _orcamento_por_categoria(valores_por_mes: dict[str, float], meses_historico: list[str]) -> dict:
    serie = [valores_por_mes.get(mes, 0.0) for mes in meses_historico]
    total_historico = sum(serie)
    media_historica_mensal = round(total_historico / len(serie), 2)

    projecao = projetar_tendencia_linear(serie, _MESES_PROJECAO)
    # Categoria com menos de 2 meses de histórico não tem tendência
    # calculável (mesma guarda de `projetar_tendencia_linear`) — usa a
    # média histórica repetida em vez de esconder a categoria da lista.
    orcamento_sugerido = (
        round(sum(projecao), 2) if projecao else round(media_historica_mensal * _MESES_PROJECAO, 2)
    )
    variacao_percentual = (
        round((orcamento_sugerido - total_historico) / total_historico * 100, 2) if total_historico else 0.0
    )

    return {
        "media_historica_mensal": media_historica_mensal,
        "total_historico_12_meses": round(total_historico, 2),
        "orcamento_sugerido_proximo_ano": orcamento_sugerido,
        "variacao_percentual": variacao_percentual,
    }


def _buscar_orcamentos(filiais: list[str]) -> list[dict]:
    meses_historico = _janela_meses_historico(_MESES_HISTORICO)
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    sql = _QUERY.replace("__FILIAL_IN__", clausula_filial)

    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, mes_inicio=meses_historico[0], **binds_filial)
        linhas = cursor.fetchall()

    por_categoria: dict[tuple[str, str], dict[str, float]] = {}
    for natureza_codigo, natureza_descricao, mes, total in linhas:
        chave = (natureza_codigo, natureza_descricao)
        por_categoria.setdefault(chave, {})[mes] = _comum.serializar(total)

    resultado = [
        {
            "natureza_codigo": natureza_codigo,
            "natureza_descricao": natureza_descricao,
            **_orcamento_por_categoria(valores_por_mes, meses_historico),
        }
        for (natureza_codigo, natureza_descricao), valores_por_mes in por_categoria.items()
    ]
    resultado.sort(key=lambda item: item["variacao_percentual"], reverse=True)
    return resultado


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/orcamento-base-zero/exportar", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def exportar_orcamento_base_zero_route(request: Request, usuario: dict) -> Response:
        """RELATÓRIO: Orçamento Base Zero — exportação em Excel."""
        filiais = _comum.filiais_da_query(request)
        if filiais is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        dados = _buscar_orcamentos(filiais)
        _comum.registrar_acesso(usuario, "orcamento_base_zero:exportar", len(dados))
        linhas = [tuple(item[coluna] for coluna in _COLUNAS) for item in dados]
        conteudo_xlsx = gerar_xlsx(_COLUNAS, linhas, titulo="Orçamento Base Zero")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="orcamento_base_zero.xlsx"',
                **CORS_HEADERS,
            },
        )

    @mcp.custom_route("/api/financeiro/orcamento-base-zero", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def listar_orcamento_base_zero_route(request: Request, usuario: dict) -> JSONResponse:
        """RELATÓRIO: Orçamento Base Zero — endpoint JSON usado pela tela."""
        filiais = _comum.filiais_da_query(request)
        if filiais is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        dados = _buscar_orcamentos(filiais)
        _comum.registrar_acesso(usuario, "orcamento_base_zero:listar", len(dados))
        return JSONResponse(dados, headers=CORS_HEADERS)
