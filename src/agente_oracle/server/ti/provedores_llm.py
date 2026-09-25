"""Rotas HTTP do cadastro de LLM (`tools/ia/provedores_llm.py`) — listar,
criar, editar, apagar e ativar. Só desenvolvedor acessa, travado no
DECORATOR de cada rota (não só checado dentro da função, como o resto do
TI) — aqui tem chave de API de verdade, então o fechamento tem que ser
mais rígido desde a entrada. A chave nunca volta pro navegador depois de
salva: GET devolve só `api_key_configurada: bool`; editar sem mandar uma
chave nova mantém a que já estava lá."""

from decimal import Decimal, InvalidOperation

from anyio import to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_desenvolvedor
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.ia import configuracoes_provedor, provedores_llm
from agente_oracle.tools.ia.provedores_llm import ProvedorLLM, ProvedorLlmJaExiste

_CAMPOS_TEXTO_OBRIGATORIOS = ("nome", "base_url", "modelo")
_CAMPOS_ATUALIZAVEIS = (
    "nome",
    "tipo_conexao",
    "base_url",
    "api_key",
    "projeto_id",
    "modelo",
    "estilo_api",
    "preco_entrada_por_1k",
    "preco_saida_por_1k",
    "moeda",
)


def _preco_valido(bruto) -> Decimal | None:
    if isinstance(bruto, bool) or not isinstance(bruto, int | float | str):
        return None
    try:
        valor = Decimal(str(bruto))
    except InvalidOperation:
        return None
    return valor if valor.is_finite() and valor >= 0 else None


def _provedor_para_json(provedor: ProvedorLLM, id_ativo: int | None) -> dict:
    return {
        "id": provedor.id,
        "nome": provedor.nome,
        "tipo_conexao": provedor.tipo_conexao,
        "base_url": provedor.base_url,
        "api_key_configurada": bool(provedor.api_key),
        "projeto_id": provedor.projeto_id,
        "modelo": provedor.modelo,
        "estilo_api": provedor.estilo_api,
        "preco_entrada_por_1k": float(provedor.preco_entrada_por_1k),
        "preco_saida_por_1k": float(provedor.preco_saida_por_1k),
        "moeda": provedor.moeda,
        "ativo": provedor.id == id_ativo,
        "criado_em": provedor.criado_em.isoformat(),
    }


def _erro(mensagem: str, status_code: int) -> Response:
    return JSONResponse({"erro": mensagem}, status_code=status_code, headers=CORS_HEADERS)


def _listar() -> Response:
    id_ativo = configuracoes_provedor.provedor_llm_ativo_id()
    linhas = [_provedor_para_json(provedor, id_ativo) for provedor in provedores_llm.listar()]
    return JSONResponse(linhas, headers=CORS_HEADERS)


def _validar_campos_comuns(corpo: dict, exigir_obrigatorios: bool) -> str | None:
    if exigir_obrigatorios:
        for campo in _CAMPOS_TEXTO_OBRIGATORIOS:
            if not str(corpo.get(campo, "")).strip():
                return f"Informe {campo}."
    if "tipo_conexao" in corpo and not provedores_llm.tipo_conexao_valido(corpo["tipo_conexao"]):
        return 'Informe tipo_conexao como "ollama" ou "openai_compativel".'
    if "estilo_api" in corpo and not provedores_llm.estilo_api_valido(corpo["estilo_api"]):
        return 'Informe estilo_api como "chat_completions" ou "responses".'
    for campo in ("preco_entrada_por_1k", "preco_saida_por_1k"):
        if campo in corpo and _preco_valido(corpo[campo]) is None:
            return f"Informe {campo} como um número >= 0."
    return None


def _criar(corpo: dict) -> Response:
    mensagem = _validar_campos_comuns(corpo, exigir_obrigatorios=True)
    if mensagem:
        return _erro(mensagem, 400)

    try:
        provedor = provedores_llm.criar(
            nome=str(corpo["nome"]).strip(),
            tipo_conexao=corpo.get("tipo_conexao", "openai_compativel"),
            base_url=str(corpo["base_url"]).strip(),
            api_key=str(corpo.get("api_key", "")).strip(),
            projeto_id=str(corpo.get("projeto_id", "")).strip(),
            modelo=str(corpo["modelo"]).strip(),
            estilo_api=corpo.get("estilo_api", "chat_completions"),
            preco_entrada_por_1k=_preco_valido(corpo.get("preco_entrada_por_1k", 0)) or Decimal(0),
            preco_saida_por_1k=_preco_valido(corpo.get("preco_saida_por_1k", 0)) or Decimal(0),
            moeda=str(corpo.get("moeda") or "R$").strip(),
        )
    except ProvedorLlmJaExiste as erro:
        return _erro(str(erro), 400)

    id_ativo = configuracoes_provedor.provedor_llm_ativo_id()
    return JSONResponse(_provedor_para_json(provedor, id_ativo), status_code=201, headers=CORS_HEADERS)


def _atualizar(id_provedor_bruto: str, corpo: dict) -> Response:
    try:
        id_provedor = int(id_provedor_bruto)
    except ValueError:
        return _erro("Provedor não encontrado.", 404)

    mensagem = _validar_campos_comuns(corpo, exigir_obrigatorios=False)
    if mensagem:
        return _erro(mensagem, 400)

    campos = {campo: corpo[campo] for campo in _CAMPOS_ATUALIZAVEIS if campo in corpo}
    for campo in ("nome", "base_url", "modelo", "api_key", "projeto_id", "moeda"):
        if campo in campos:
            campos[campo] = str(campos[campo]).strip()
    for campo in ("preco_entrada_por_1k", "preco_saida_por_1k"):
        if campo in campos:
            campos[campo] = _preco_valido(campos[campo])

    try:
        provedor = provedores_llm.atualizar(id_provedor, **campos)
    except ProvedorLlmJaExiste as erro:
        return _erro(str(erro), 400)
    if provedor is None:
        return _erro("Provedor não encontrado.", 404)

    id_ativo = configuracoes_provedor.provedor_llm_ativo_id()
    return JSONResponse(_provedor_para_json(provedor, id_ativo), headers=CORS_HEADERS)


def _remover(id_provedor_bruto: str) -> Response:
    try:
        id_provedor = int(id_provedor_bruto)
    except ValueError:
        return _erro("Provedor não encontrado.", 404)

    if not provedores_llm.remover(id_provedor):
        return _erro("Provedor não encontrado.", 404)
    # Se era o ativo, ninguém fica ativo — cai no Ollama padrão do `.env`
    # (ver `tools/ia/cliente_protegido.py`), nunca aponta pra um id morto.
    if configuracoes_provedor.provedor_llm_ativo_id() == id_provedor:
        configuracoes_provedor.definir_provedor_llm_ativo_id(None)
    return JSONResponse({"ok": True}, headers=CORS_HEADERS)


def _desativar() -> Response:
    """Volta o ponteiro pra `None` — mesmo estado de "nenhum LLM cadastrado
    ativo" (`criar_cliente_protegido` cai no Ollama padrão do `.env`), sem
    apagar nenhum provedor cadastrado."""
    configuracoes_provedor.definir_provedor_llm_ativo_id(None)
    return _listar()


def _ativar(id_provedor_bruto: str) -> Response:
    try:
        id_provedor = int(id_provedor_bruto)
    except ValueError:
        return _erro("Provedor não encontrado.", 404)

    if provedores_llm.buscar(id_provedor) is None:
        return _erro("Provedor não encontrado.", 404)
    configuracoes_provedor.definir_provedor_llm_ativo_id(id_provedor)
    return _listar()


def registrar(mcp) -> None:
    @mcp.custom_route("/api/ti/provedores-llm", methods=["GET", "POST", "OPTIONS"])
    @rota_protegida("GET, POST, OPTIONS", exigir=exigir_desenvolvedor)
    async def provedores_llm_route(request: Request, usuario: dict) -> Response:
        if request.method == "GET":
            return await to_thread.run_sync(_listar)
        corpo = await request.json()
        return await to_thread.run_sync(_criar, corpo)

    # Registrada ANTES de `/{id}` de propósito — mesmo número de segmentos
    # de path, "desativar" bateria com o padrão `{id}` se essa viesse depois.
    @mcp.custom_route("/api/ti/provedores-llm/desativar", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=exigir_desenvolvedor)
    async def provedor_llm_desativar_route(request: Request, usuario: dict) -> Response:
        return await to_thread.run_sync(_desativar)

    @mcp.custom_route("/api/ti/provedores-llm/{id}", methods=["PATCH", "DELETE", "OPTIONS"])
    @rota_protegida("PATCH, DELETE, OPTIONS", exigir=exigir_desenvolvedor)
    async def provedor_llm_detalhe_route(request: Request, usuario: dict) -> Response:
        id_provedor = request.path_params["id"]
        if request.method == "DELETE":
            return await to_thread.run_sync(_remover, id_provedor)
        corpo = await request.json()
        return await to_thread.run_sync(_atualizar, id_provedor, corpo)

    @mcp.custom_route("/api/ti/provedores-llm/{id}/ativar", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=exigir_desenvolvedor)
    async def provedor_llm_ativar_route(request: Request, usuario: dict) -> Response:
        return await to_thread.run_sync(_ativar, request.path_params["id"])
