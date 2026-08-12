"""RELATÓRIO: Resumo Bancário / Movimento Financeiro Diário (FINR530)

Tradução do ADVPL (`FINR530.PRW`) — para uma data de referência única
(`MV_PAR01`), lista, por conta bancária, o saldo inicial, as entradas, as
saídas, as aplicações financeiras do dia e o saldo disponível resultante. É
o "resumo do dia" — prima do FINR470/Extrato Bancário
(`extrato_bancario.py`), que lista o extrato linha a linha; aqui é só o
totalizador por conta, para uma data só.

Migrado do Oracle transacional do Protheus (SA6010/SE5010) para o STAGE
(SCIENCE_PROD, ETL/BI) — ver `db/views/financeiro_science.sql`/README
("Views curadas do Financeiro") pro modelo geral.

Duas descobertas específicas deste relatório:
- **`STAGE.SALDOBANCARIO` tem histórico diário real** (uma linha por conta
  por dia, anos de profundidade) — é exatamente o snapshot `SE8` ("Saldos
  Bancários") que a versão anterior (contra Postgres de teste) não tinha e
  por isso reconstruía o saldo inicial somando toda a movimentação anterior
  à mão. Aqui usamos o snapshot direto (linha mais recente antes da data de
  referência), mais fiel ao ADVPL original.
- **Conta bancária não é escopada pela filial de 4 dígitos** —
  `SALDOBANCARIO.CODIGOEMPRESA` guarda o "grupo de filiais" de 2 dígitos
  (`STAGE.EMPRESA.GRUPOLOJA`, ex: '01' agrupa 0101-0106), não a filial
  específica. Ou seja, contas bancárias são compartilhadas entre filiais do
  mesmo grupo — por isso o filtro de filial aqui primeiro resolve os grupos
  correspondentes (CTE `grupos`) antes de achar as contas.

O que ficou de fora (documentado, não é atalho silencioso):
- Multi-moeda (`MV_PAR02`/`MV_PAR04`) — não encontramos taxa de conversão
  associada a `MOVIMENTACAOFINANCEIRA`/`SALDOBANCARIO` no STAGE.
- **"Considera Limite de Crédito" (`MV_PAR03`/`A6_LIMCRED`)** — não achamos
  campo de limite de crédito em `STAGE.SALDOBANCARIO` nem em nenhuma tabela
  de conta bancária do STAGE. O parâmetro continua aceito na rota (pra não
  quebrar a tela), mas não tem mais efeito nenhum — sempre soma zero.
- Caixa de loja e cheques com tratamento especial — mesma simplificação já
  documentada no FINR470.

O que TEM fidelidade real:
- Filtro de data de referência (obrigatório) — só a data inicial é usada
  como referência, igual ao MV_PAR01 original (que é uma data única).
- Exclui os mesmos tipos de documento que não são movimentação bancária real
  (`TIPODOCUMENTO NOT IN (...)`, valor zero) — mesma lista do FINR470.
- **Aplicações financeiras** tratadas à parte: lançamento com
  `TIPODOCUMENTO='AP'` soma ao total de aplicações quando é uma saída de
  caixa (`TIPOMOVIMENTACAO='PAGAR'`, dinheiro indo pra aplicação) e subtrai
  quando é uma entrada (`TIPOMOVIMENTACAO='RECEBER'`, resgate) — mesma
  lógica do bloco `IF/ELSE` do ADVPL original. Aplicações não entram nos
  totais de entradas/saídas comuns.
- **Saldo disponível** = saldo inicial + entradas - saídas - aplicações —
  mesma fórmula do `nDisponiv` original (sem o termo de limite de crédito,
  ver acima).
"""

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.db.connection import get_connection
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_financeiro
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

# Mesma lista do FINR470: tipos de documento que são baixas de título, não
# movimentação bancária real.
_TIPODOC_EXCLUIDOS_IN = "('DC','JR','MT','CM','D2','J2','M2','V2','C2','CP','TL','BA','I2','EI','VA')"

_QUERY = """
-- =====================================================================
-- RELATORIO: Resumo Bancario / Movimento Financeiro Diario (FINR530)
-- versao STAGE (sem multi-moeda/limite de credito/caixa de loja)
-- =====================================================================
WITH grupos AS (
    SELECT DISTINCT grupoloja
    FROM STAGE.empresa
    WHERE excluido = 0 AND TRIM(codigo) IN __FILIAL_IN__
),
contas AS (
    SELECT DISTINCT sb.codigobanco, sb.codigoagencia, sb.codigoconta
    FROM STAGE.saldobancario sb
    JOIN grupos g ON TRIM(sb.codigoempresa) = g.grupoloja
    WHERE sb.excluido = 0
),
saldo_inicial AS (
    SELECT c.codigobanco, c.codigoagencia, c.codigoconta,
        (
            SELECT TO_NUMBER(sb2.valorsaldoatual)
            FROM STAGE.saldobancario sb2
            WHERE sb2.codigobanco = c.codigobanco AND sb2.codigoagencia = c.codigoagencia
              AND sb2.codigoconta = c.codigoconta AND sb2.excluido = 0
              AND sb2.datasaldoatual = (
                  SELECT MAX(sb3.datasaldoatual) FROM STAGE.saldobancario sb3
                  WHERE sb3.codigobanco = c.codigobanco AND sb3.codigoagencia = c.codigoagencia
                    AND sb3.codigoconta = c.codigoconta AND sb3.excluido = 0
                    AND sb3.datasaldoatual < TO_DATE(:data_ini, 'YYYYMMDD')
              )
              AND ROWNUM = 1
        ) AS valor
    FROM contas c
),
movimento_dia AS (
    SELECT c.codigobanco, c.codigoagencia, c.codigoconta,
        COALESCE(SUM(CASE WHEN mf.tipomovimentacao = 'RECEBER' AND mf.tipodocumento <> 'AP' THEN mf.valor ELSE 0 END), 0) AS entradas,
        COALESCE(SUM(CASE WHEN mf.tipomovimentacao = 'PAGAR' AND mf.tipodocumento <> 'AP' THEN mf.valor ELSE 0 END), 0) AS saidas,
        COALESCE(SUM(
            CASE WHEN mf.tipodocumento = 'AP'
                THEN CASE WHEN mf.tipomovimentacao = 'PAGAR' THEN mf.valor ELSE -mf.valor END
                ELSE 0
            END
        ), 0) AS aplicacoes
    FROM contas c
    LEFT JOIN STAGE.movimentacaofinanceira mf
        ON mf.banco = c.codigobanco AND mf.agencia = c.codigoagencia AND mf.conta = c.codigoconta
       AND mf.excluido = 0
       AND mf.datadisponibilizacao = TO_DATE(:data_ini, 'YYYYMMDD')
       AND mf.valor <> 0
       AND mf.tipodocumento NOT IN __TIPODOC_EXCLUIDOS__
    GROUP BY c.codigobanco, c.codigoagencia, c.codigoconta
)
SELECT
    c.codigobanco,
    c.codigoagencia,
    c.codigoconta,
    bb.descricao AS nome_conta,
    COALESCE(si.valor, 0) AS saldo_inicial,
    COALESCE(md.entradas, 0) AS entradas,
    COALESCE(md.saidas, 0) AS saidas,
    COALESCE(md.aplicacoes, 0) AS aplicacoes,
    (
        COALESCE(si.valor, 0) + COALESCE(md.entradas, 0) - COALESCE(md.saidas, 0) - COALESCE(md.aplicacoes, 0)
    ) AS saldo_disponivel
FROM contas c
LEFT JOIN saldo_inicial si ON si.codigobanco = c.codigobanco AND si.codigoagencia = c.codigoagencia AND si.codigoconta = c.codigoconta
LEFT JOIN movimento_dia md ON md.codigobanco = c.codigobanco AND md.codigoagencia = c.codigoagencia AND md.codigoconta = c.codigoconta
LEFT JOIN STAGE.bancobacen bb ON TO_CHAR(bb.codigo) = LPAD(TRIM(c.codigobanco), 3, '0')
ORDER BY c.codigobanco, c.codigoagencia, c.codigoconta
"""

_CAMPOS_OPCIONAIS = ("data_ini", "data_fim")


def _buscar_movimento(filiais: list[str], opcionais: dict[str, str]) -> tuple[list[str], list[tuple]]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)

    opcionais.pop("data_fim", None)

    sql = _QUERY.replace("__FILIAL_IN__", clausula_filial).replace(
        "__TIPODOC_EXCLUIDOS__", _TIPODOC_EXCLUIDOS_IN
    )

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
    if not opcionais.get("data_ini"):
        return None

    return filiais, opcionais


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/movimento-financeiro-diario/exportar", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
    async def exportar_movimento_financeiro_diario_route(request: Request, usuario: dict) -> Response:
        """RELATÓRIO: Resumo Bancário / Movimento Financeiro Diário (FINR530) — exportação em Excel."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe filial e a data de referência."}, status_code=400, headers=CORS_HEADERS
            )

        colunas, linhas = _buscar_movimento(*parametros)
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Resumo Bancário / Movimento Financeiro Diário")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="movimento_financeiro_diario.xlsx"',
                **CORS_HEADERS,
            },
        )

    @mcp.custom_route("/api/financeiro/movimento-financeiro-diario", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
    async def listar_movimento_financeiro_diario_route(request: Request, usuario: dict) -> JSONResponse:
        """RELATÓRIO: Resumo Bancário / Movimento Financeiro Diário (FINR530) — endpoint JSON usado pela tela."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe filial e a data de referência."}, status_code=400, headers=CORS_HEADERS
            )

        colunas, linhas = _buscar_movimento(*parametros)
        dados = [
            dict(zip(colunas, (_comum.serializar(valor) for valor in linha), strict=True)) for linha in linhas
        ]
        return JSONResponse(dados, headers=CORS_HEADERS)
