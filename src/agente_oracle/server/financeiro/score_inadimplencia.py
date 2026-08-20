"""Rota do Score de Inadimplência — comportamento de pagamento mora em
`agent/financeiro/score_inadimplencia.py`, clima regional em
`agent/financeiro/clima_regional.py` (cache em `tools/financeiro/
clima_cache.py`, TTL de 24h por município). Este módulo só busca dado do
Oracle, monta o client HTTP da Open-Meteo e a resposta HTTP — roda sob
demanda, nunca em background, mesmo espírito de `despesas_suspeitas.py`."""

from datetime import date, timedelta

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.financeiro.clima_regional import (
    IndicadorClima,
    buscar_indicador_clima,
    buscar_indicador_clima_por_coordenadas,
)
from agente_oracle.agent.financeiro.score_inadimplencia import (
    SafraCliente,
    ScoreInadimplencia,
    TituloReceberLiquidado,
    calcular_score,
    comportamento_por_cliente,
    safra_ativa_por_cliente,
)
from agente_oracle.db.connection import get_connection
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_financeiro
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in
from agente_oracle.tools.financeiro import clima_cache, localizacao_cliente

_DIAS_HISTORICO = 180
_TIMEOUT_HTTP_SEGUNDOS = 10.0


def _data(valor):
    return valor.date() if hasattr(valor, "date") else valor


def _buscar_liquidados(filiais: list[str], desde: date) -> list[TituloReceberLiquidado]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    sql = f"""
        SELECT cliente_codigo, cliente_nome, data_vencimento, data_baixa
        FROM vw_titulos_receber
        WHERE filial IN {clausula_filial}
          AND data_baixa IS NOT NULL
          AND data_baixa >= :desde
    """
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, desde=desde, **binds_filial)
        linhas = cursor.fetchall()
    return [
        TituloReceberLiquidado(
            cliente_codigo=cliente_codigo,
            cliente_nome=cliente_nome,
            data_vencimento=_data(data_vencimento),
            data_baixa=_data(data_baixa),
        )
        for (cliente_codigo, cliente_nome, data_vencimento, data_baixa) in linhas
    ]


def _buscar_municipios(clientes_codigos: list[str]) -> dict[str, tuple[str, str]]:
    """cliente_codigo -> (municipio_nome, uf), só pros clientes informados
    — cliente sem município cadastrado não entra no dict (clima fica
    indisponível pra ele)."""
    if not clientes_codigos:
        return {}
    clausula_cliente, binds_cliente = clausula_in("cliente", clientes_codigos)
    sql = f"""
        SELECT codigo, municipio_nome, estado
        FROM vw_clientes
        WHERE codigo IN {clausula_cliente}
    """
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, **binds_cliente)
        linhas = cursor.fetchall()
    return {codigo: (municipio_nome, estado) for codigo, municipio_nome, estado in linhas if municipio_nome}


def _buscar_safras(clientes_codigos: list[str]) -> list[SafraCliente]:
    """Um registro por compra de produto com cultura definida, pros
    clientes informados — mesmo padrão de `_buscar_municipios`."""
    if not clientes_codigos:
        return []
    clausula_cliente, binds_cliente = clausula_in("cliente", clientes_codigos)
    sql = f"""
        SELECT cliente_codigo, cultura, safra_codigo, safra_descricao, safra_inicio, safra_fim, data_compra
        FROM vw_safra_cliente
        WHERE cliente_codigo IN {clausula_cliente}
    """
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, **binds_cliente)
        linhas = cursor.fetchall()
    return [
        SafraCliente(
            cliente_codigo=cliente_codigo,
            cultura=cultura,
            safra_codigo=safra_codigo,
            safra_descricao=safra_descricao,
            safra_inicio=_data(safra_inicio),
            safra_fim=_data(safra_fim),
            data_compra=_data(data_compra),
        )
        for (
            cliente_codigo,
            cultura,
            safra_codigo,
            safra_descricao,
            safra_inicio,
            safra_fim,
            data_compra,
        ) in linhas
    ]


async def _climas_por_municipio(
    municipios: set[tuple[str, str]],
) -> dict[tuple[str, str], IndicadorClima]:
    """Um indicador por município ÚNICO (não por cliente) — usa cache
    (`tools/financeiro/clima_cache.py`) antes de chamar a Open-Meteo de
    verdade."""
    climas: dict[tuple[str, str], IndicadorClima] = {}
    async with httpx.AsyncClient(timeout=_TIMEOUT_HTTP_SEGUNDOS) as http_client:
        for municipio_nome, uf in municipios:
            indicador = clima_cache.buscar_cache(municipio_nome, uf)
            if indicador is None:
                indicador = await buscar_indicador_clima(http_client, municipio_nome, uf)
                clima_cache.salvar_cache(indicador)
            climas[(municipio_nome, uf)] = indicador
    return climas


def _rotulo_localizacao(localizacao: localizacao_cliente.LocalizacaoCliente) -> str:
    """Texto pra exibir/logar essa localização — usado como rótulo do
    indicador de clima e como chave do cache (`clima_cache`)."""
    if localizacao.cidade:
        return f"{localizacao.bairro}, {localizacao.cidade}" if localizacao.bairro else localizacao.cidade
    return f"{localizacao.latitude}, {localizacao.longitude}"


async def _climas_por_cliente_cadastrado(
    localizacoes: dict[str, localizacao_cliente.LocalizacaoCliente],
) -> dict[str, IndicadorClima]:
    """Um indicador por CLIENTE (não por localização única) — cliente com
    localização própria cadastrada e resolvida pula tanto a geocodificação
    quanto o fallback de município (mais rápido e mais preciso). Também
    passa pelo cache de clima (`clima_cache`), chaveado pelo texto
    cadastrado como se fosse um "município" — evita rebater a Open-Meteo
    pro mesmo cliente a cada cálculo."""
    resolvidas = {
        cliente_codigo: localizacao
        for cliente_codigo, localizacao in localizacoes.items()
        if localizacao.resolvido
    }
    if not resolvidas:
        return {}

    climas: dict[str, IndicadorClima] = {}
    async with httpx.AsyncClient(timeout=_TIMEOUT_HTTP_SEGUNDOS) as http_client:
        for cliente_codigo, localizacao in resolvidas.items():
            rotulo = _rotulo_localizacao(localizacao)
            indicador = clima_cache.buscar_cache(rotulo, "cadastro")
            if indicador is None:
                indicador = await buscar_indicador_clima_por_coordenadas(
                    http_client, localizacao.latitude, localizacao.longitude, rotulo, "cadastro"
                )
                clima_cache.salvar_cache(indicador)
            climas[cliente_codigo] = indicador
    return climas


def _localizacao_para_json(localizacao: localizacao_cliente.LocalizacaoCliente | None) -> dict | None:
    if localizacao is None:
        return None
    return {
        "cidade": localizacao.cidade,
        "bairro": localizacao.bairro,
        "latitude": localizacao.latitude,
        "longitude": localizacao.longitude,
        "resolvido": localizacao.resolvido,
    }


def _score_para_json(
    score: ScoreInadimplencia, localizacao: localizacao_cliente.LocalizacaoCliente | None
) -> dict:
    return {
        "cliente_codigo": score.cliente_codigo,
        "cliente_nome": score.cliente_nome,
        "score": score.score,
        "comportamento": {
            "percentual_atraso_recente": score.comportamento.percentual_atraso_recente,
            "percentual_atraso_anterior": score.comportamento.percentual_atraso_anterior,
            "dias_atraso_medio": score.comportamento.dias_atraso_medio,
            "tendencia": score.comportamento.tendencia,
        },
        "clima": (
            {
                "municipio_nome": score.clima.municipio_nome,
                "uf": score.clima.uf,
                "classificacao": score.clima.classificacao,
            }
            if score.clima is not None
            else None
        ),
        "safra_ativa": (
            {
                "cultura": score.safra_ativa.cultura,
                "safra_descricao": score.safra_ativa.safra_descricao,
            }
            if score.safra_ativa is not None
            else None
        ),
        "fatores": list(score.fatores),
        "localizacao": _localizacao_para_json(localizacao),
    }


def _apenas_com_risco(scores: list[ScoreInadimplencia]) -> list[ScoreInadimplencia]:
    """A tela só quer ver quem tem algum indício de risco — cliente 100%
    em dia (score exatamente 0, sem atraso e sem clima/safra pesando)
    fica de fora, mas qualquer sinal, por menor que seja, já aparece.
    Função pura, sem I/O, só pra deixar essa regra testável sem banco."""
    return [score for score in scores if score.score > 0]


def _coordenada_valida(latitude: float | None, longitude: float | None) -> bool:
    if latitude is None or longitude is None:
        return False
    return -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0


def _resolver_clima(
    cliente_codigo: str,
    municipios_por_cliente: dict[str, tuple[str, str]],
    climas_por_municipio: dict[tuple[str, str], IndicadorClima],
    climas_por_cliente_cadastrado: dict[str, IndicadorClima],
) -> IndicadorClima | None:
    """Localização cadastrada e resolvida pro cliente tem prioridade;
    faltando ela (sem cadastro, ou cadastro que não resolveu), cai pro
    centro do município. Função pura, sem I/O, só pra deixar essa regra
    testável sem banco/HTTP — mesmo espírito de `_apenas_com_risco`."""
    clima_cadastrado = climas_por_cliente_cadastrado.get(cliente_codigo)
    if clima_cadastrado is not None:
        return clima_cadastrado
    chave_municipio = municipios_por_cliente.get(cliente_codigo)
    return climas_por_municipio.get(chave_municipio) if chave_municipio else None


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/score-inadimplencia", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def score_inadimplencia_route(request: Request, usuario: dict) -> Response:
        """Comportamento de pagamento (`vw_titulos_receber`, últimos
        `_DIAS_HISTORICO` dias) + clima regional (Open-Meteo — localização
        cadastrada manualmente pro cliente, se houver e tiver resolvido; senão
        o centro do município via `vw_clientes`) — indicador composto por
        regra, sem IA (ver docstring de `agent/financeiro/
        score_inadimplencia.py`). Só devolve cliente com algum indício de
        risco (score > 0, ver `_apenas_com_risco`) — cliente 100% em dia
        não aparece na lista."""
        filiais = _comum.filiais_da_query(request)
        if filiais is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        desde = date.today() - timedelta(days=_DIAS_HISTORICO)
        hoje = date.today()
        comportamentos = comportamento_por_cliente(_buscar_liquidados(filiais, desde), hoje)

        clientes_codigos = [c.cliente_codigo for c in comportamentos]
        municipios_por_cliente = _buscar_municipios(clientes_codigos)
        municipios_unicos = set(municipios_por_cliente.values())
        climas_por_municipio = await _climas_por_municipio(municipios_unicos)

        localizacoes_por_cliente = localizacao_cliente.buscar_varios(clientes_codigos)
        climas_por_cliente_cadastrado = await _climas_por_cliente_cadastrado(localizacoes_por_cliente)

        safras_ativas = safra_ativa_por_cliente(_buscar_safras(clientes_codigos), hoje)

        scores = []
        for comportamento in comportamentos:
            cliente_codigo = comportamento.cliente_codigo
            clima = _resolver_clima(
                cliente_codigo, municipios_por_cliente, climas_por_municipio, climas_por_cliente_cadastrado
            )

            safra_ativa = safras_ativas.get(cliente_codigo)
            scores.append(calcular_score(comportamento, clima, safra_ativa))
        scores = _apenas_com_risco(scores)
        scores.sort(key=lambda score: score.score, reverse=True)

        _comum.registrar_acesso(usuario, "score_inadimplencia:calcular", len(scores))
        return JSONResponse(
            [_score_para_json(score, localizacoes_por_cliente.get(score.cliente_codigo)) for score in scores],
            headers=CORS_HEADERS,
        )

    @mcp.custom_route("/api/financeiro/score-inadimplencia/localizacao", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=exigir_modulo_financeiro)
    async def localizacao_cliente_route(request: Request, usuario: dict) -> Response:
        """Cadastra (ou atualiza) a localização de um cliente pro cálculo de
        clima do score — cidade (+ bairro opcional, geocodificados) ou
        coordenadas diretas. Exige cidade OU coordenadas válidas. Não
        conseguindo geocodificar cidade/bairro, ainda assim salva (pra não
        perder o que a pessoa preencheu) e avisa que o clima segue usando o
        município enquanto isso."""
        corpo = await request.json()
        cliente_codigo = str(corpo.get("cliente_codigo") or "").strip()
        cidade = str(corpo.get("cidade") or "").strip() or None
        bairro = str(corpo.get("bairro") or "").strip() or None
        latitude = corpo.get("latitude")
        longitude = corpo.get("longitude")
        latitude = float(latitude) if isinstance(latitude, (int, float)) else None
        longitude = float(longitude) if isinstance(longitude, (int, float)) else None

        if not cliente_codigo:
            return JSONResponse({"erro": "Informe cliente_codigo."}, status_code=400, headers=CORS_HEADERS)
        coordenada_informada = latitude is not None or longitude is not None
        if not cidade and not coordenada_informada:
            return JSONResponse(
                {"erro": "Informe cidade ou coordenadas."}, status_code=400, headers=CORS_HEADERS
            )
        if coordenada_informada and not _coordenada_valida(latitude, longitude):
            return JSONResponse(
                {"erro": "Coordenadas inválidas — informe latitude e longitude."},
                status_code=400,
                headers=CORS_HEADERS,
            )

        async with httpx.AsyncClient(timeout=_TIMEOUT_HTTP_SEGUNDOS) as http_client:
            localizacao = await localizacao_cliente.salvar(
                http_client, cliente_codigo, cidade, bairro, latitude, longitude
            )

        _comum.registrar_acesso(usuario, "score_inadimplencia:cadastrar_localizacao", 1)
        return JSONResponse(_localizacao_para_json(localizacao), headers=CORS_HEADERS)
