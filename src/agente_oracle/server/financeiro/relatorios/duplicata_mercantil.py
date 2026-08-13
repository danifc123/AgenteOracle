"""RELATÓRIO: Impressão de Duplicata Mercantil (FINR04)

Tradução do ADVPL (fMontaTela/fPopula) — os filtros originais eram
MV_PAR01..MV_PAR09, todos opcionais ("Vazio=TODOS"), igual mantido aqui: só a
filial é obrigatória (e agora aceita seleção múltipla, igual ao Fluxo de
Caixa Realizado). Os demais campos ficam vazios quando não usados.

Migrado do Oracle transacional do Protheus (SE1010/SA1010/SA3010) para o
STAGE (SCIENCE_PROD, ETL/BI) — `STAGE.DUPLICATA` é uma tabela dedicada pra
esse conceito (já tem `DUPLICATAASSINADA`, direto), então usamos ela em vez
de reconstruir de `CONTARECEBER`.

ATENÇÃO — `nome_cliente` foi removido: `DUPLICATA.CLIENTE` guarda só o
código-base do cliente (9 dígitos), sem o sufixo de loja que
`PESSOA.CODIGO` carrega embutido (13 dígitos) — e o mesmo cliente pode ter
várias "lojas" (várias linhas de PESSOA com o mesmo prefixo). Testado: 0%
de match tentando `PESSOA.CODIGO = DUPLICATA.CLIENTE` (esperado, já que os
tamanhos nem batem) — e não dá pra escolher a loja certa por prefixo sem
arriscar mostrar o nome de outra loja do mesmo cliente. Fica só o código até
acharmos uma chave de ligação confiável.

`VALOR`/`SALDO` em `STAGE.DUPLICATA` vêm como texto (`NVARCHAR2`), não
número — por isso o `TO_NUMBER(...)` explícito.

Filtros opcionais usam `:bind IS NULL OR :bind = ''` em vez de `:bind = ''`
puro (nem `COALESCE(:bind, '') = ''` resolve — o literal `''` também é NULL
no Oracle) — achado ao validar esta migração, ver `_comum.filtro_vazio` e o
"ACHADO IMPORTANTE" no topo de `_comum.py`.

O filtro "Prefixo" também ficou sem fonte de dado — `STAGE.DUPLICATA` não
tem coluna de prefixo de documento (só `DUPLICATA`, o número em si). O
campo continua aceito na tela, mas não filtra nada até acharmos onde esse
dado mora no STAGE (mesma situação do filtro "Loja", ver `cadastros.py`).
"""

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.db.connection import get_connection
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

_QUERY = """
-- =====================================================================
-- RELATORIO: Impressão de Duplicata Mercantil (FINR04)
-- Tradução do ADVPL (fPopula) — filial(is) obrigatória(s), demais opcionais
-- =====================================================================
SELECT
    TRIM(d.filial)                    AS filial,
    d.duplicata,
    d.duplicataassinada,
    TRIM(d.tipo)                      AS tipo,
    TRIM(d.cliente)                   AS cliente_codigo,
    CAST(d.dataemissao AS DATE)       AS data_emissao,
    CAST(d.datavencimento AS DATE)    AS data_vencimento,
    TO_NUMBER(d.valor)                AS valor,
    TO_NUMBER(d.saldo)                AS saldo,
    TRIM(d.vendedor)                  AS vendedor_codigo,
    vp.nome                           AS nome_consultor
FROM STAGE.duplicata d
LEFT JOIN STAGE.pessoa vp
    ON vp.codigo = d.vendedor AND vp.sourcetable = 'SA3010'
WHERE d.excluido = 0
  AND TRIM(d.filial) IN __FILIAL_IN__
  AND (:cliente IS NULL OR :cliente = '' OR TRIM(d.cliente) = :cliente)
  AND (
        :vencto_ini IS NULL OR :vencto_ini = '' OR :vencto_fim IS NULL OR :vencto_fim = ''
     OR d.datavencimento BETWEEN TO_DATE(NULLIF(:vencto_ini, ''), 'YYYYMMDD') AND TO_DATE(NULLIF(:vencto_fim, ''), 'YYYYMMDD')
  )
  AND (:tipo IS NULL OR :tipo = '' OR TRIM(d.tipo) = :tipo)
  AND (:vendedor IS NULL OR :vendedor = '' OR TRIM(d.vendedor) = :vendedor)
  AND (
        :status_assinatura IS NULL OR :status_assinatura = ''
     OR (:status_assinatura = '1' AND d.duplicataassinada = 'SIM')
     OR (:status_assinatura = '2' AND d.duplicataassinada <> 'SIM')
  )
ORDER BY d.filial, d.cliente, d.duplicata
"""

_CAMPOS_OPCIONAIS = (
    "cliente",
    "vencto_ini",
    "vencto_fim",
    "tipo",
    "vendedor",
    "status_assinatura",
)


def _buscar_duplicatas(filiais: list[str], opcionais: dict[str, str]) -> tuple[list[str], list[tuple]]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    sql = _QUERY.replace("__FILIAL_IN__", clausula_filial)

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

    return filiais, _comum.parametros_opcionais(request, _CAMPOS_OPCIONAIS)


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/duplicata-mercantil/exportar", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def exportar_duplicatas_route(request: Request, usuario: dict) -> Response:
        """RELATÓRIO: Impressão de Duplicata Mercantil (FINR04) — exportação em Excel."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        colunas, linhas = _buscar_duplicatas(*parametros)
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Duplicata Mercantil")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="duplicata_mercantil.xlsx"',
                **CORS_HEADERS,
            },
        )

    @mcp.custom_route("/api/financeiro/duplicata-mercantil", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def listar_duplicatas_route(request: Request, usuario: dict) -> JSONResponse:
        """RELATÓRIO: Impressão de Duplicata Mercantil (FINR04) — endpoint JSON usado pela tela."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        colunas, linhas = _buscar_duplicatas(*parametros)
        dados = [
            dict(zip(colunas, (_comum.serializar(valor) for valor in linha), strict=True)) for linha in linhas
        ]
        return JSONResponse(dados, headers=CORS_HEADERS)
