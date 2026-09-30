"""Client de IA "protegido" — mesma interface pra qualquer provedor por
baixo (`chat`, `embed`), usado só na instanciação (`server/*.py`). Os
agentes que já existem (`agent/ti/qualidade_chamado.py` etc.) recebem esse
client como recebiam o de sempre e continuam chamando `.chat()`/`.embed()`
exatamente como sempre — não sabem que isso existe, nem qual provedor está
por trás, então nenhum deles precisa mudar.

Intercepta toda chamada antes de sair da máquina: sanitiza (se a política
desse ponto de chamada pedir — decidida por quem instancia, não aqui) e
audita, sempre. Nenhuma IA extra no meio — sanitizar é regex, auditar é um
INSERT no Postgres local, nada de chamada de rede a mais.

Dois motores possíveis hoje: `ollama.AsyncClient` (padrão) e
`ClienteOpenAICompativel` (qualquer LLM cadastrado compatível com OpenAI)
— pra `dominio in ("ti", "rh")`, QUAL provedor usar vem do cadastro do
usuário (`tools/ia/provedores_llm.py`, tela `/ti/provedores`), lido do
Postgres a cada chamada, não em cache, então trocar de LLM ativo não
precisa reiniciar o servidor nem editar código. Sem nenhum LLM cadastrado
ativo, cai no Ollama padrão do `.env` — mesmo comportamento de antes desse
cadastro existir, pra nunca quebrar uma instalação nova/vazia.

Chat e embedding têm ponteiros de "ativo" INDEPENDENTES
(`configuracoes_provedor.provedor_llm_ativo_id`/`_embedding_ativo_id`) —
`criar_cliente_protegido` resolve o de chat, `criar_cliente_embedding_protegido`
o de embedding. Precisa disso porque nem todo provedor sabe fazer as duas
coisas (ex: os modelos OCI de embedding puro cadastrados pra corrigir
categoria de chamado não têm endpoint de chat, e o guardrail em
`server/ti/provedores_llm.py::_ativar` nem deixa um provedor assim virar
"o ativo" de chat) — sem os dois ponteiros, o time inteiro ficaria sem
conversar toda vez que alguém ativasse um modelo só de embedding.

Financeiro/Auditoria NUNCA olham o cadastro — tocam dado real do Oracle e
continuam 100% no caminho antigo (Ollama do `.env`, por domínio), protegido
por `config.py::validar_ollama_host_seguro`, até o fornecedor cadastrado
ser validado pra esse tipo de dado."""

import logging

import oci
from ollama import AsyncClient
from openai import AsyncOpenAI

from agente_oracle.config import (
    DominioIA,
    Settings,
    ollama_api_key_do_dominio,
    ollama_host_do_dominio,
    ollama_model_do_dominio,
)
from agente_oracle.tools.ia import auditoria_externa, configuracoes_provedor, provedores_llm
from agente_oracle.tools.ia.cliente_oci_nativo import ClienteOciNativo
from agente_oracle.tools.ia.cliente_openai_compativel import ClienteOpenAICompativel
from agente_oracle.tools.ia.provedores_llm import ProvedorLLM
from agente_oracle.tools.ia.saneamento import sanitizar_dado_sensivel, sanitizar_mensagens

# Domínios que podem usar o cadastro de LLM — os outros dois (financeiro,
# auditoria) tocam dado real do Oracle, ver docstring do módulo.
_DOMINIOS_COM_CADASTRO: tuple[DominioIA, ...] = ("ti", "rh")

# Nome genérico de propósito — nunca aparece pro usuário como "Ollama"
# especificamente: o motor por trás desse fallback É o `ollama.AsyncClient`
# (ver `criar_cliente_protegido` abaixo), mas o rótulo mostrado em "Uso de
# IA"/auditoria não deve amarrar o usuário a um produto específico — a
# empresa pode trocar de modelo/vendor sem essa label ficar desatualizada
# (pedido do Daniel, 2026-09-28).
_PROVEDOR_PADRAO = "Modelo de IA (padrão)"

logger = logging.getLogger(__name__)

# Sentinela pra chamada de IA sem usuário logado por trás — o poller
# automático de chamados (`server/ti/chamados.py::iniciar_poller_verificar_chamados`)
# e o webhook do GLPI (`server/ti/webhook_glpi.py`, autenticado só por
# segredo compartilhado) não têm sessão nenhuma. Único lugar que define
# essa string, pra quem chama importar em vez de cada um inventar a
# própria — usado no relatório "por usuário" da página Tokens do TI.
USUARIO_SISTEMA = "sistema"


class TetoTokensExcedidoError(Exception):
    """Levantada ANTES da chamada de rede sair (ver `ClienteIAProtegido.
    chat`/`.embed`), quando o domínio já gastou hoje >= o teto configurado
    pra ele (`server/ia/teto_tokens.py`) — trava de verdade, não só aviso.
    O poller de Chamados (`server/ti/chamados.py`) já isola falha por
    chamado num `except Exception` genérico, então cai nesse guarda-chuva
    sem precisar de tratamento novo lá; rotas interativas (`server/ti/
    seguranca.py`, `server/rh/busca.py`, `server/rh/candidatos.py`)
    tratam explicitamente pra devolver um 429 amigável em vez de deixar
    estourar como 500 cru."""

    def __init__(self, dominio: str):
        self.dominio = dominio
        super().__init__(
            f'Teto diário de tokens do departamento "{dominio}" foi atingido. '
            "Tente novamente amanhã, ou peça pro administrador do módulo ajustar o teto."
        )


class ClienteIAProtegido:
    def __init__(
        self,
        cliente_real: AsyncClient,
        dominio: DominioIA,
        host: str,
        sanitizar: bool,
        teto_diario: int,
        provedor: str,
        usuario_id: str,
    ):
        self._cliente = cliente_real
        self._dominio = dominio
        self._host = host
        self._sanitizar = sanitizar
        self._teto_diario = teto_diario
        self._provedor = provedor
        self._usuario_id = usuario_id

    async def chat(self, *, messages, **kwargs):
        self._verificar_teto_tokens()
        mensagens = sanitizar_mensagens(messages) if self._sanitizar else messages
        resposta = await self._cliente.chat(messages=mensagens, **kwargs)
        self._registrar_e_avisar(_texto_das_mensagens(mensagens), kwargs.get("model", ""), resposta)
        return resposta

    async def embed(self, *, input, **kwargs):
        self._verificar_teto_tokens()
        texto = sanitizar_dado_sensivel(input) if self._sanitizar else input
        resposta = await self._cliente.embed(input=texto, **kwargs)
        self._registrar_e_avisar(texto, kwargs.get("model", ""), resposta)
        return resposta

    def _verificar_teto_tokens(self) -> None:
        """Roda ANTES de qualquer chamada de rede (ver `chat`/`embed`
        acima) — compara o que o domínio já gastou HOJE (`auditoria_
        externa.tokens_hoje`, soma de chamadas já concluídas e
        registradas) contra o teto cadastrado pra ele. `0`/sem
        configuração significa sem teto, nunca bloqueia. Não estima o
        custo da chamada que está prestes a sair — só olha o acumulado
        até aqui, então uma última chamada grande ainda pode, na
        prática, fazer o dia terminar um pouco acima do teto."""
        teto = configuracoes_provedor.teto_tokens_diario(self._dominio)
        if teto <= 0:
            return
        if auditoria_externa.tokens_hoje(self._dominio) >= teto:
            raise TetoTokensExcedidoError(self._dominio)

    def _registrar_e_avisar(self, texto: str, modelo: str, resposta) -> None:
        # `getattr` porque nem toda resposta traz os três — Ollama pode
        # omitir em respostas parciais, `tokens_raciocinio` só existe pro
        # gpt-oss-120b, e o normalizador da OCI já usa os mesmos nomes de
        # atributo (ver cliente_openai_compativel.py), então este trecho
        # não precisa saber qual provedor respondeu.
        auditoria_externa.registrar(
            self._dominio,
            self._host,
            texto,
            self._provedor,
            modelo,
            getattr(resposta, "prompt_eval_count", None),
            getattr(resposta, "eval_count", None),
            getattr(resposta, "tokens_raciocinio", None),
            self._usuario_id,
        )
        contagem = auditoria_externa.contagem_hoje(self._dominio)
        if contagem > self._teto_diario:
            logger.warning(
                "Domínio de IA '%s' passou do teto diário de chamadas externas (%d > %d) — "
                "só um alerta, nada foi bloqueado.",
                self._dominio,
                contagem,
                self._teto_diario,
            )


def _texto_das_mensagens(mensagens: list[dict]) -> str:
    return "\n".join(mensagem["content"] for mensagem in mensagens)


def _provedor_llm_ativo(dominio: DominioIA) -> provedores_llm.ProvedorLLM | None:
    """`None` pra domínio sem cadastro (financeiro/auditoria) ou sem
    nenhum LLM ativo (nada cadastrado ainda, ou o cadastrado foi
    removido) — os dois casos caem no Ollama padrão do `.env`."""
    if dominio not in _DOMINIOS_COM_CADASTRO:
        return None
    id_ativo = configuracoes_provedor.provedor_llm_ativo_id()
    if id_ativo is None:
        return None
    return provedores_llm.buscar(id_ativo)


def construir_cliente_llm(provedor: ProvedorLLM) -> tuple[object, str]:
    """Dado um `ProvedorLLM` QUALQUER — ativo ou não —, monta o client
    real certo e devolve junto o `host` (só pra log/auditoria). Usado
    tanto pelo provedor ATIVO (`criar_cliente_protegido` abaixo) quanto
    pela rota de testar um cadastro sem ativar
    (`server/ti/provedores_llm.py::_testar`) — não sabe nada sobre "qual
    é o ativo", isso é responsabilidade de quem chama."""
    if provedor.tipo_conexao == "ollama":
        cliente_real = AsyncClient(
            host=provedor.base_url,
            headers={"Authorization": f"Bearer {provedor.api_key}"} if provedor.api_key else {},
        )
        return cliente_real, provedor.base_url
    if provedor.tipo_conexao == "openai_compativel":
        cliente_real = ClienteOpenAICompativel(
            AsyncOpenAI(base_url=provedor.base_url, api_key=provedor.api_key, project=provedor.projeto_id or None),
            provedor.estilo_api,
        )
        return cliente_real, provedor.base_url
    # "oci_nativo" — autenticação por assinatura RSA, não bearer token; a
    # chave privada vem do cadastro (`credenciais_extra`) e nunca é escrita
    # em disco, só usada em memória. `key_content` no lugar de `key_file`
    # (mesmo dict que `oci.config.from_file` devolveria) — o SDK monta o
    # signer sozinho a partir disso, mesmo padrão do exemplo oficial da
    # Oracle (ticket #1834414), sem precisar instanciar `oci.signer.Signer`
    # à mão.
    credenciais = provedor.credenciais_extra or {}
    config = {
        "tenancy": credenciais.get("tenancy_ocid", ""),
        "user": credenciais.get("user_ocid", ""),
        "fingerprint": credenciais.get("fingerprint", ""),
        "key_content": credenciais.get("chave_privada", ""),
        "region": credenciais.get("regiao", ""),
    }
    endpoint = f"https://inference.generativeai.{credenciais.get('regiao', '')}.oci.oraclecloud.com"
    cliente_oci = oci.generative_ai_inference.GenerativeAiInferenceClient(
        config=config,
        service_endpoint=endpoint,
        retry_strategy=oci.retry.NoneRetryStrategy(),
        timeout=(10, 240),
    )
    cliente_real = ClienteOciNativo(cliente_oci, credenciais.get("compartment_id", ""))
    return cliente_real, endpoint


def criar_cliente_protegido(
    settings: Settings, dominio: DominioIA, sanitizar: bool, usuario_id: str
) -> ClienteIAProtegido:
    """Substitui `AsyncClient(host=settings.ollama_host)` direto — olha o
    LLM cadastrado ativo (`tools/ia/provedores_llm.py`, só pra TI/RH) e
    monta o client real certo (`construir_cliente_llm`), já envolto na
    proteção. O modelo continua vindo de fora (`modelo_ia_ativo`),
    exatamente como já era passado hoje pra
    `avaliar_chamado`/`classificar_categoria` — este client só cuida de
    onde a chamada vai, não de qual modelo pedir nela. `usuario_id` é
    `usuario["sub"]` de quem chamou, ou `USUARIO_SISTEMA` quando não tem
    sessão por trás (poller, webhook do GLPI) — vai pro relatório "por
    usuário" da página Tokens do TI."""
    ativo = _provedor_llm_ativo(dominio)
    if ativo is None:
        host = ollama_host_do_dominio(settings, dominio)
        chave = ollama_api_key_do_dominio(settings, dominio)
        cliente_real = AsyncClient(host=host, headers={"Authorization": f"Bearer {chave}"} if chave else {})
        provedor = _PROVEDOR_PADRAO
    else:
        cliente_real, host = construir_cliente_llm(ativo)
        provedor = ativo.nome
    return ClienteIAProtegido(
        cliente_real, dominio, host, sanitizar, settings.teto_diario_ia_externa, provedor, usuario_id
    )


def modelo_ia_ativo(settings: Settings, dominio: DominioIA) -> str:
    """O modelo do LLM cadastrado ativo; sem cadastro (financeiro/auditoria,
    ou nada ativo ainda) cai no modelo padrão do Ollama pro domínio."""
    ativo = _provedor_llm_ativo(dominio)
    if ativo is not None:
        return ativo.modelo
    return ollama_model_do_dominio(settings, dominio)


def _provedor_llm_embedding_ativo(dominio: DominioIA) -> provedores_llm.ProvedorLLM | None:
    """Mesma ideia de `_provedor_llm_ativo`, mas pro ponteiro de EMBEDDING
    (`configuracoes_provedor.provedor_llm_embedding_ativo_id`) — os dois
    são independentes de propósito, ver docstring do módulo de
    configuração."""
    if dominio not in _DOMINIOS_COM_CADASTRO:
        return None
    id_ativo = configuracoes_provedor.provedor_llm_embedding_ativo_id()
    if id_ativo is None:
        return None
    return provedores_llm.buscar(id_ativo)


def criar_cliente_embedding_protegido(
    settings: Settings, dominio: DominioIA, sanitizar: bool, usuario_id: str
) -> ClienteIAProtegido:
    """Mesma ideia de `criar_cliente_protegido`, mas resolve o provedor de
    EMBEDDING ativo — ponteiro independente do chat ativo, porque nem todo
    provedor sabe fazer as duas coisas (`capacidades`; ex: os modelos OCI
    de embedding puro, que não têm endpoint de chat). Sem embedding
    cadastrado ativo, cai no MESMO client do chat ativo — mesmo
    comportamento de antes desse ponteiro existir (`classificar_categoria`
    tentava `.embed()` no client de chat e, salvo ele saber fazer as duas
    coisas, caía em `EmbeddingNaoSuportado`; ver `agent/ti/roteamento_chamado.py`).
    Usado só pela correção de categoria de chamado hoje
    (`server/ti/chamados.py::processar_chamado_novo`)."""
    ativo = _provedor_llm_embedding_ativo(dominio)
    if ativo is None:
        return criar_cliente_protegido(settings, dominio, sanitizar, usuario_id)
    cliente_real, host = construir_cliente_llm(ativo)
    return ClienteIAProtegido(
        cliente_real, dominio, host, sanitizar, settings.teto_diario_ia_externa, ativo.nome, usuario_id
    )


def modelo_embedding_ativo(settings: Settings, dominio: DominioIA) -> str:
    """O modelo do provedor de EMBEDDING cadastrado ativo; sem um
    cadastrado (ou domínio sem cadastro), cai no modelo de embedding
    padrão do `.env` — mesmo valor usado antes desse ponteiro existir."""
    ativo = _provedor_llm_embedding_ativo(dominio)
    if ativo is not None:
        return ativo.modelo
    return settings.ollama_embedding_model
