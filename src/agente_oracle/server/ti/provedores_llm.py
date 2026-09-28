"""Rotas HTTP do cadastro de LLM (`tools/ia/provedores_llm.py`) — listar,
criar, editar, apagar, ativar e testar. Só desenvolvedor acessa, travado no
DECORATOR de cada rota (não só checado dentro da função, como o resto do
TI) — aqui tem chave de API/chave privada de verdade, então o fechamento
tem que ser mais rígido desde a entrada. A credencial nunca volta pro
navegador depois de salva: GET devolve só `api_key_configurada`/
`credenciais_configuradas: bool`; editar sem mandar uma credencial nova
mantém a que já estava lá.

`testar` (`POST .../{id}/testar`) dispara uma chamada real contra UM
cadastro específico sem tocar no ponteiro de "ativo" — deixa confirmar
que uma credencial recém-cadastrada funciona antes de considerar ativá-la,
sem arriscar derrubar o provedor que o resto do TI/RH já está usando (só
1 fica ativo por vez, ver `tools/ia/provedores_llm.py`)."""

from decimal import Decimal, InvalidOperation

from anyio import to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_desenvolvedor
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.ia import cliente_protegido, configuracoes_provedor, provedores_llm
from agente_oracle.tools.ia.provedores_llm import ProvedorLLM, ProvedorLlmJaExiste

_CAMPOS_TEXTO_OBRIGATORIOS = ("nome", "base_url", "modelo")
# `oci_nativo` não pede `base_url` digitado — é calculado a partir da
# `regiao` em `credenciais_extra` (ver `_base_url_para_criar`).
_CAMPOS_TEXTO_OBRIGATORIOS_OCI_NATIVO = ("nome", "modelo")
_CAMPOS_CREDENCIAIS_OCI_NATIVO = (
    "user_ocid",
    "fingerprint",
    "tenancy_ocid",
    "regiao",
    "compartment_id",
    "chave_privada",
)
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
    "capacidades",
    "credenciais_extra",
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
        "capacidades": provedor.capacidades,
        # Mesmo espírito de `api_key_configurada` — `credenciais_extra`
        # (chave privada da OCI, etc.) nunca volta pro navegador.
        "credenciais_configuradas": bool(provedor.credenciais_extra),
        # Só um aviso pro front decidir quando sugerir renovar — nunca
        # expira/bloqueia nada sozinho (ver docstring de
        # tools/ia/provedores_llm.py).
        "credencial_atualizada_em": provedor.credencial_atualizada_em.isoformat(),
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
    tipo_conexao = corpo.get("tipo_conexao", "openai_compativel")
    if exigir_obrigatorios:
        campos = (
            _CAMPOS_TEXTO_OBRIGATORIOS_OCI_NATIVO if tipo_conexao == "oci_nativo" else _CAMPOS_TEXTO_OBRIGATORIOS
        )
        for campo in campos:
            if not str(corpo.get(campo, "")).strip():
                return f"Informe {campo}."
    if "tipo_conexao" in corpo and not provedores_llm.tipo_conexao_valido(corpo["tipo_conexao"]):
        return 'Informe tipo_conexao como "ollama", "openai_compativel" ou "oci_nativo".'
    if "estilo_api" in corpo and not provedores_llm.estilo_api_valido(corpo["estilo_api"]):
        return 'Informe estilo_api como "chat_completions" ou "responses".'
    for campo in ("preco_entrada_por_1k", "preco_saida_por_1k"):
        if campo in corpo and _preco_valido(corpo[campo]) is None:
            return f"Informe {campo} como um número >= 0."
    if "capacidades" in corpo and not provedores_llm.capacidades_validas(corpo["capacidades"]):
        return 'Informe capacidades como uma lista não vazia com "chat" e/ou "embedding".'
    if exigir_obrigatorios and tipo_conexao == "oci_nativo":
        credenciais = corpo.get("credenciais_extra")
        if not isinstance(credenciais, dict):
            return "Informe credenciais_extra (user_ocid, fingerprint, tenancy_ocid, regiao, compartment_id, chave_privada)."
        for campo in _CAMPOS_CREDENCIAIS_OCI_NATIVO:
            if not str(credenciais.get(campo, "")).strip():
                return f"Informe {campo} em credenciais_extra."
    return None


def _base_url_para_criar(corpo: dict, tipo_conexao: str) -> str:
    """`oci_nativo` calcula o endereço a partir da `regiao` em
    `credenciais_extra` — não pede pra digitar duas vezes a mesma coisa
    (a região já define o endpoint univocamente)."""
    if tipo_conexao != "oci_nativo":
        return str(corpo.get("base_url", "")).strip()
    regiao = corpo["credenciais_extra"]["regiao"].strip()
    return f"https://inference.generativeai.{regiao}.oci.oraclecloud.com"


def _criar(corpo: dict) -> Response:
    mensagem = _validar_campos_comuns(corpo, exigir_obrigatorios=True)
    if mensagem:
        return _erro(mensagem, 400)

    tipo_conexao = corpo.get("tipo_conexao", "openai_compativel")
    credenciais_extra = corpo.get("credenciais_extra") if tipo_conexao == "oci_nativo" else None

    try:
        provedor = provedores_llm.criar(
            nome=str(corpo["nome"]).strip(),
            tipo_conexao=tipo_conexao,
            base_url=_base_url_para_criar(corpo, tipo_conexao),
            api_key=str(corpo.get("api_key", "")).strip(),
            projeto_id=str(corpo.get("projeto_id", "")).strip(),
            modelo=str(corpo["modelo"]).strip(),
            estilo_api=corpo.get("estilo_api", "chat_completions"),
            preco_entrada_por_1k=_preco_valido(corpo.get("preco_entrada_por_1k", 0)) or Decimal(0),
            preco_saida_por_1k=_preco_valido(corpo.get("preco_saida_por_1k", 0)) or Decimal(0),
            moeda=str(corpo.get("moeda") or "R$").strip(),
            capacidades=corpo.get("capacidades") or ["chat"],
            credenciais_extra=credenciais_extra,
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

    provedor = provedores_llm.buscar(id_provedor)
    if provedor is None:
        return _erro("Provedor não encontrado.", 404)
    # Só 1 provedor ativo por vez no sistema inteiro (chat + embedding
    # juntos, ver docstring do módulo de tools) — ativar um sem capacidade
    # de chat quebraria toda conversa do TI/RH sem aviso nenhum.
    if "chat" not in provedor.capacidades:
        return _erro("Esse provedor só serve pra embedding, não pode virar o provedor ativo do sistema.", 400)
    configuracoes_provedor.definir_provedor_llm_ativo_id(id_provedor)
    return _listar()


async def _testar(id_provedor_bruto: str) -> Response:
    """Dispara UMA chamada real e barata contra ESSE provedor
    especificamente — nunca mexe no ponteiro de ativo (`configuracoes_provedor`).
    Deixa confirmar que uma credencial recém-cadastrada funciona de
    verdade sem precisar ativar (e arriscar derrubar o provedor que o
    resto do TI/RH já está usando)."""
    try:
        id_provedor = int(id_provedor_bruto)
    except ValueError:
        return _erro("Provedor não encontrado.", 404)

    provedor = await to_thread.run_sync(provedores_llm.buscar, id_provedor)
    if provedor is None:
        return _erro("Provedor não encontrado.", 404)

    cliente_real, _host = cliente_protegido.construir_cliente_llm(provedor)
    try:
        if "embedding" in provedor.capacidades:
            await cliente_real.embed(input="teste de conexão", model=provedor.modelo)
        else:
            await cliente_real.chat(messages=[{"role": "user", "content": "oi"}], model=provedor.modelo)
    except Exception as erro:
        return _erro(f"Falha ao testar a conexão: {erro}", 400)
    return JSONResponse({"ok": True}, headers=CORS_HEADERS)


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

    @mcp.custom_route("/api/ti/provedores-llm/{id}/testar", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=exigir_desenvolvedor)
    async def provedor_llm_testar_route(request: Request, usuario: dict) -> Response:
        return await _testar(request.path_params["id"])
