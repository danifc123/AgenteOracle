"""RELATÓRIO: Impressão de Duplicata Mercantil (FINR04)

Tradução do ADVPL (fMontaTela/fPopula) — os filtros originais eram
MV_PAR01..MV_PAR09, todos opcionais ("Vazio=TODOS"), igual mantido aqui: só a
filial é obrigatória (e agora aceita seleção múltipla, igual ao Fluxo de
Caixa Realizado). Os demais campos ficam vazios quando não usados.

Os campos E1_NOMCLI (nome do cliente) e E1_NMVEND1 (nome do consultor), que
no ADVPL eram buscados linha a linha via GetAdvFVal, viraram LEFT JOIN com
SA1010 (clientes) e SA3 (vendedores/consultores — nesse banco de teste a
tabela não tem o sufixo "010").

MV_PAR09 (status da assinatura) era um combo 1/2/3 (Assinadas/Não
assinadas/Ambas); "Ambas" nunca filtrava nada no original, então virou o
valor vazio ('') aqui.

Atenção: só roda com DB_BACKEND=postgres (mesma observação do Fluxo de Caixa
Realizado — sintaxe de cast ::tipo). Os campos de data (vencimento) usam
NULLIF pra aceitar vazio sem quebrar o cast ::date. E1_VENCTO nesse banco de
teste é VARCHAR (formato "YYYYMMDD"), por isso também precisa do ::date antes
de comparar com os limites do período.
"""

from decimal import Decimal

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.db.connection import get_connection
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.auth.dependencia import exigir_usuario
from agente_oracle.server.cors import CORS_HEADERS, resposta_preflight
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

_QUERY = """
-- =====================================================================
-- RELATORIO: Impressão de Duplicata Mercantil (FINR04)
-- Tradução do ADVPL (fPopula) — filial(is) obrigatória(s), demais opcionais
-- =====================================================================
SELECT
    se1.e1_filial,
    se1.e1_prefixo,
    se1.e1_xdupass,
    se1.e1_num,
    se1.e1_parcela,
    se1.e1_tipo,
    se1.e1_naturez,
    se1.e1_cliente,
    se1.e1_loja,
    sa1.a1_nome                AS nome_cliente,
    se1.e1_nomcli               AS propriedade,
    se1.e1_emissao,
    se1.e1_vencto,
    se1.e1_vencrea,
    se1.e1_valor,
    se1.e1_hist,
    se1.e1_vend1,
    sa3.a3_nome                AS nome_consultor
FROM se1010 se1
LEFT JOIN sa1010 sa1
    ON sa1.a1_cod = se1.e1_cliente
   AND sa1.a1_loja = se1.e1_loja
LEFT JOIN sa3 sa3
    ON sa3.a3_cod = se1.e1_vend1
WHERE COALESCE(se1.d_e_l_e_t_, ' ') = ' '
  AND TRIM(se1.e1_filial) IN __FILIAL_IN__
  AND (:cliente = '' OR TRIM(se1.e1_cliente) = :cliente)
  AND (:loja = '' OR TRIM(se1.e1_loja) = :loja)
  AND (
        :vencto_ini = '' OR :vencto_fim = ''
     OR se1.e1_vencto::date BETWEEN NULLIF(:vencto_ini, '')::date AND NULLIF(:vencto_fim, '')::date
  )
  AND (:prefixo = '' OR TRIM(se1.e1_prefixo) = :prefixo)
  AND (:tipo = '' OR TRIM(se1.e1_tipo) = :tipo)
  AND (:vendedor = '' OR TRIM(se1.e1_vend1) = :vendedor)
  AND (
        :status_assinatura = ''
     OR (:status_assinatura = '1' AND TRIM(se1.e1_xdupass) = 'S')
     OR (:status_assinatura = '2' AND (TRIM(se1.e1_xdupass) = 'N' OR se1.e1_xdupass = ' '))
  )
ORDER BY se1.e1_filial, se1.e1_cliente, se1.e1_loja, se1.e1_prefixo, se1.e1_num, se1.e1_parcela, se1.e1_tipo
"""

_CAMPOS_OPCIONAIS = ("cliente", "loja", "vencto_ini", "vencto_fim", "prefixo", "tipo", "vendedor", "status_assinatura")


def _serializar(valor):
    return float(valor) if isinstance(valor, Decimal) else valor


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
    filial_bruto = request.query_params.get("filial", "").strip()
    filiais = [item.strip() for item in filial_bruto.split(",") if item.strip()]
    if not filiais:
        return None

    opcionais = {chave: request.query_params.get(chave, "").strip() for chave in _CAMPOS_OPCIONAIS}
    return filiais, opcionais


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/duplicata-mercantil", methods=["GET", "OPTIONS"])
    async def listar_duplicatas_route(request: Request) -> JSONResponse:
        """RELATÓRIO: Impressão de Duplicata Mercantil (FINR04) — endpoint JSON usado pela tela."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS)

        colunas, linhas = _buscar_duplicatas(*parametros)
        dados = [dict(zip(colunas, (_serializar(valor) for valor in linha))) for linha in linhas]
        return JSONResponse(dados, headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/duplicata-mercantil/exportar", methods=["GET", "OPTIONS"])
    async def exportar_duplicatas_route(request: Request) -> Response:
        """RELATÓRIO: Impressão de Duplicata Mercantil (FINR04) — exportação em Excel."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS)

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
