"""RELATÓRIO: Relação de Baixas (FINR190)

Tradução do ADVPL (`FINR190.PRX`, ~2.700 linhas) — lista as baixas
(liquidações) de títulos — a receber ou a pagar, conforme `tipo_movimento`
(equivalente ao MV_PAR11) — dentro de uma faixa de datas, enriquecidas com
dados do título original.

Migrado do Oracle transacional do Protheus (SE5010/SE1010/SE2010/SA1010/
SA2010/SED010/SA6010) para o STAGE (SCIENCE_PROD, ETL/BI) —
`STAGE.MOVIMENTACAOFINANCEIRA` no lugar de `SE5010`, `STAGE.CONTARECEBER`/
`STAGE.CONTAPAGAR` no lugar de `SE1010`/`SE2010`. Ver
`db/views/financeiro_science.sql`/README ("Views curadas do Financeiro")
pro modelo geral de PESSOA/SOURCETABLE.

O que ficou de fora nesta migração (não tinha equivalente confirmado no
STAGE):
- **Abatimento** — a versão anterior reconstruía isso somando o saldo de
  títulos-filho via `E1_TITPAI`/`E2_TITPAI` (aliás, já dava sempre 0 no
  banco de teste, a fórmula só estava "pronta"). `STAGE.CONTARECEBER`/
  `STAGE.CONTAPAGAR` não têm coluna equivalente a título-pai — **fica
  sempre 0**, mesmo tratamento que os outros relatórios do módulo dão a
  campos sem fonte confirmada.
- **Valor Acessório (VA)** — a versão anterior calculava um valor real via
  `FK6010`/`FK1010`/`FK2010` (ligados por `E5_IDORIG`, um id de origem sem
  prefixo/número/parcela). Sem equivalente no STAGE (mesma investigação que
  já descartou isso para `retencao_impostos.py`) — **fica sempre 0**.
- **Filtro "Loja"** e **"Data de Digitação"** — mesma limitação estrutural
  documentada em `cadastros.py` (loja não existe separada do código da
  pessoa) e nenhuma coluna de "data de digitação" distinta encontrada em
  `STAGE.MOVIMENTACAOFINANCEIRA` (só data de movimentação/vencimento/
  disponibilização).
- **Retenção de impostos na baixa** — já era sempre 0 antes (dependia de
  parametrização não confirmável); continua 0.

O que TEM fidelidade real:
- Filtros em faixa (banco, natureza, cliente/fornecedor, prefixo, lote,
  vencimento do título) + filial + faixa de data de baixa (obrigatória).
- **Valor original** = valor cheio do título (`CONTARECEBER.VALORTOTAL`/
  `CONTAPAGAR.VALORTOTAL`) — mesmo comportamento do ADVPL original (mostra
  o valor do título inteiro em cada linha de baixa, não a fração paga).
- **Total baixado** = soma real de `VALOR` do(s) registro(s) de
  `MOVIMENTACAOFINANCEIRA` que formam esse evento, agrupados por filial +
  prefixo + número + parcela + tipo + pessoa + tipo de movimentação (mesmo
  espírito do agrupamento original, sem `E5_SEQ`/`E5_NUMCHEQ` — não achamos
  equivalente desses dois campos no STAGE, então o agrupamento aqui é um
  pouco mais grosso; pode juntar em uma linha só duas baixas do mesmo
  título/pessoa no mesmo dia que no ADVPL original apareceriam separadas).
- **Juros/multa e desconto reais**, somados de `VALORJUROS`+`VALORMULTA` e
  `VALORDESCONTO` — campos de texto no STAGE (`NVARCHAR2`), convertidos com
  `TO_NUMBER`.

Datas em `MOVIMENTACAOFINANCEIRA`/`CONTARECEBER`/`CONTAPAGAR` já são
`TIMESTAMP` de verdade no STAGE (não precisa de `TO_DATE`/YYYYMMDD).

ATENÇÃO charset: comparações envolvendo colunas `NVARCHAR2` (`MOTIVOBAIXA`,
`BENEFICIARIO`) contra literal solto (`''`, `'DSD'`) dão `ORA-12704`
(character set mismatch) — usar literal nacional (`N''`, `N'DSD'`). Mesmo
problema documentado em `financeiro_science.sql` (`vw_movimento_bancario`).

Filtros opcionais usam `:bind IS NULL OR :bind = ''` (não `:bind = ''`
puro) — ver o "ACHADO IMPORTANTE" no topo de `_comum.py`. Contra Postgres
esse padrão sozinho não basta (`AmbiguousParameter`) — a query passa por
`_comum.aplicar_cast_binds_opcionais()` antes de rodar.

`TO_NUMBER(coluna)` de 1 argumento (`valorjuros`/`valormulta`/
`valorcorrigido`/`valordesconto`) e `TO_CHAR(coluna_numerica)` de 1
argumento (`bb.codigo` no JOIN com `bancobacen`) são sintaxe exclusiva do
Oracle — trocados por `_comum.numero_coluna()`/`_comum.texto_numero()`
(achado populando o banco fictício, ver "Oracle vs Postgres" em
`MAPA_BANCOS_LOCAL.md`).
"""

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.db.connection import get_connection
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

_ORDENS = {
    "data_baixa": "b.data_baixa",
    "banco": "b.banco, b.agencia, b.conta",
    "natureza": "b.codigonatureza",
    "clifor": "nome_clifor",
    "numero": "b.numero",
    "lote": "b.lote",
}

_TIPO_MOVIMENTO_SQL = {"R": "RECEBER", "P": "PAGAR"}

_QUERY = """
-- =====================================================================
-- RELATORIO: Relacao de Baixas (FINR190) — versao STAGE
-- (abatimento e valor acessorio sem fonte confirmada, sempre 0)
-- =====================================================================
WITH baixas AS (
    SELECT
        TRIM(mf.filialorigem) AS filial, TRIM(mf.prefixo) AS prefixo, TRIM(mf.numero) AS numero,
        TRIM(mf.parcela) AS parcela, TRIM(mf.tipo) AS tipo, TRIM(mf.codigopessoa) AS codigopessoa,
        mf.tipomovimentacao,
        MIN(mf.tipodocumento) AS tipodocumento,
        MIN(COALESCE(NULLIF(mf.motivobaixa, N''), N'NOR')) AS motivobaixa,
        MIN(mf.banco) AS banco,
        MIN(mf.agencia) AS agencia,
        MIN(mf.conta) AS conta,
        MIN(mf.codigonatureza) AS codigonatureza,
        MIN(mf.beneficiario) AS beneficiario,
        MIN(mf.historico) AS historico,
        MIN(CAST(mf.datamovimentacao AS DATE)) AS data_baixa,
        MIN(mf.lote) AS lote,
        SUM(mf.valor) AS valor_total,
        SUM(COALESCE(__NUMERO_VALORJUROS__, 0) + COALESCE(__NUMERO_VALORMULTA__, 0)) AS juros_multa,
        SUM(COALESCE(__NUMERO_VALORCORRIGIDO__, 0)) AS correcao,
        SUM(COALESCE(__NUMERO_VALORDESCONTO__, 0)) AS desconto
    FROM STAGE.movimentacaofinanceira mf
    WHERE mf.excluido = 0
      AND mf.tipomovimentacao = :tipo_movimento
      AND COALESCE(mf.motivobaixa, N'') <> N'DSD'
      AND TRIM(mf.filialorigem) IN __FILIAL_IN__
      AND mf.datamovimentacao BETWEEN TO_DATE(:data_baixa_ini, 'YYYYMMDD') AND TO_DATE(:data_baixa_fim, 'YYYYMMDD')
      AND (:banco_ini IS NULL OR :banco_ini = '' OR mf.banco >= :banco_ini)
      AND (:banco_fim IS NULL OR :banco_fim = '' OR mf.banco <= :banco_fim)
      AND (:natureza_ini IS NULL OR :natureza_ini = '' OR mf.codigonatureza >= :natureza_ini)
      AND (:natureza_fim IS NULL OR :natureza_fim = '' OR mf.codigonatureza <= :natureza_fim)
      AND (:clifor_ini IS NULL OR :clifor_ini = '' OR mf.codigopessoa >= :clifor_ini)
      AND (:clifor_fim IS NULL OR :clifor_fim = '' OR mf.codigopessoa <= :clifor_fim)
      AND (:prefixo_ini IS NULL OR :prefixo_ini = '' OR mf.prefixo >= :prefixo_ini)
      AND (:prefixo_fim IS NULL OR :prefixo_fim = '' OR mf.prefixo <= :prefixo_fim)
      AND (:lote_ini IS NULL OR :lote_ini = '' OR COALESCE(mf.lote, N'') >= :lote_ini)
      AND (:lote_fim IS NULL OR :lote_fim = '' OR COALESCE(mf.lote, N'') <= :lote_fim)
    GROUP BY mf.filialorigem, mf.prefixo, mf.numero, mf.parcela, mf.tipo, mf.codigopessoa, mf.tipomovimentacao
)
SELECT
    b.filial,
    b.prefixo,
    b.numero,
    b.parcela,
    b.tipo,
    b.tipodocumento,
    b.tipomovimentacao,
    b.codigopessoa,
    COALESCE(p.nome, NULLIF(b.beneficiario, N'')) AS nome_clifor,
    b.codigonatureza,
    n.descricao AS nome_natureza,
    CAST((CASE WHEN b.tipomovimentacao = 'RECEBER' THEN cr.datavencimento ELSE cp.datavencimento END) AS DATE) AS vencimento,
    b.historico,
    b.data_baixa,
    (CASE WHEN b.tipomovimentacao = 'RECEBER' THEN cr.valortotal ELSE cp.valortotal END) AS valor_original,
    b.juros_multa,
    b.correcao,
    b.desconto,
    0 AS abatimento,
    0 AS imposto,
    b.valor_total AS total_baixado,
    b.banco,
    bb.descricao AS nome_banco,
    b.agencia,
    b.conta,
    b.tipodocumento AS motivo,
    b.filial AS filial_origem,
    b.lote,
    0 AS valor_acessorio
FROM baixas b
LEFT JOIN STAGE.contareceber cr ON b.tipomovimentacao = 'RECEBER' AND cr.codigopessoa = b.codigopessoa
    AND TRIM(cr.prefixo) = b.prefixo AND TRIM(cr.numero) = b.numero AND TRIM(cr.parcela) = b.parcela AND TRIM(cr.tipo) = b.tipo
LEFT JOIN STAGE.contapagar cp ON b.tipomovimentacao = 'PAGAR' AND cp.codigopessoa = b.codigopessoa
    AND TRIM(cp.prefixo) = b.prefixo AND TRIM(cp.numero) = b.numero AND TRIM(cp.parcela) = b.parcela AND TRIM(cp.tipo) = b.tipo
LEFT JOIN STAGE.pessoa p ON p.codigo = b.codigopessoa
    AND p.sourcetable = (CASE WHEN b.tipomovimentacao = 'RECEBER' THEN 'SA1010' ELSE 'SA2010' END)
LEFT JOIN STAGE.natureza n ON n.codigo = b.codigonatureza
LEFT JOIN STAGE.bancobacen bb ON __TEXTO_CODIGO_BANCO__ = LPAD(b.banco, 3, '0')
WHERE (
        :vencimento_ini IS NULL OR :vencimento_ini = '' OR :vencimento_fim IS NULL OR :vencimento_fim = ''
     OR (CASE WHEN b.tipomovimentacao = 'RECEBER' THEN cr.datavencimento ELSE cp.datavencimento END)
        BETWEEN TO_DATE(NULLIF(:vencimento_ini, ''), 'YYYYMMDD') AND TO_DATE(NULLIF(:vencimento_fim, ''), 'YYYYMMDD')
      )
ORDER BY __ORDEM__
"""

_CAMPOS_OPCIONAIS = (
    "tipo_movimento",
    "data_baixa_ini",
    "data_baixa_fim",
    "banco_ini",
    "banco_fim",
    "natureza_ini",
    "natureza_fim",
    "clifor_ini",
    "clifor_fim",
    "prefixo_ini",
    "prefixo_fim",
    "lote_ini",
    "lote_fim",
    "vencimento_ini",
    "vencimento_fim",
    "ordenar_por",
)


def _buscar_baixas(filiais: list[str], opcionais: dict[str, str]) -> tuple[list[str], list[tuple]]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)

    ordenar_por = opcionais.pop("ordenar_por", "") or "data_baixa"
    ordem_sql = _ORDENS.get(ordenar_por, _ORDENS["data_baixa"])

    tipo_movimento_curto = opcionais.get("tipo_movimento") or "R"
    if tipo_movimento_curto not in _TIPO_MOVIMENTO_SQL:
        tipo_movimento_curto = "R"
    opcionais["tipo_movimento"] = _TIPO_MOVIMENTO_SQL[tipo_movimento_curto]

    sql = (
        _QUERY.replace("__FILIAL_IN__", clausula_filial)
        .replace("__ORDEM__", ordem_sql)
        .replace("__NUMERO_VALORJUROS__", _comum.numero_coluna("mf.valorjuros"))
        .replace("__NUMERO_VALORMULTA__", _comum.numero_coluna("mf.valormulta"))
        .replace("__NUMERO_VALORCORRIGIDO__", _comum.numero_coluna("mf.valorcorrigido"))
        .replace("__NUMERO_VALORDESCONTO__", _comum.numero_coluna("mf.valordesconto"))
        .replace("__TEXTO_CODIGO_BANCO__", _comum.texto_numero("bb.codigo"))
    )
    sql = _comum.aplicar_cast_binds_opcionais(sql)

    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, **opcionais, **binds_filial)
        colunas = [descricao[0] for descricao in cursor.description]
        linhas = cursor.fetchall()
    return colunas, linhas


def _parametros_da_query(request: Request) -> tuple[list[str], dict[str, str]] | None:
    filiais = _comum.filiais_da_query(request)
    if filiais is None:
        return None

    opcionais = _comum.parametros_opcionais(request, _CAMPOS_OPCIONAIS)
    if not opcionais.get("data_baixa_ini") or not opcionais.get("data_baixa_fim"):
        return None

    return filiais, opcionais


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/relacao-baixas/exportar", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def exportar_relacao_baixas_route(request: Request, usuario: dict) -> Response:
        """RELATÓRIO: Relação de Baixas (FINR190) — exportação em Excel."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial e a faixa de data da baixa."},
                status_code=400,
                headers=CORS_HEADERS,
            )

        colunas, linhas = _buscar_baixas(*parametros)
        _comum.registrar_acesso(usuario, "relacao_baixas:exportar", len(linhas))
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Relação de Baixas")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="relacao_baixas.xlsx"',
                **CORS_HEADERS,
            },
        )

    @mcp.custom_route("/api/financeiro/relacao-baixas", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def listar_relacao_baixas_route(request: Request, usuario: dict) -> JSONResponse:
        """RELATÓRIO: Relação de Baixas (FINR190) — endpoint JSON usado pela tela."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial e a faixa de data da baixa."},
                status_code=400,
                headers=CORS_HEADERS,
            )

        colunas, linhas = _buscar_baixas(*parametros)
        _comum.registrar_acesso(usuario, "relacao_baixas:listar", len(linhas))
        dados = [
            dict(zip(colunas, (_comum.serializar(valor) for valor in linha), strict=True)) for linha in linhas
        ]
        return JSONResponse(dados, headers=CORS_HEADERS)
