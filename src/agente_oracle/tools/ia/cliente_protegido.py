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

_PROVEDOR_OLLAMA_PADRAO = "Ollama (padrão)"

logger = logging.getLogger(__name__)

# Sentinela pra chamada de IA sem usuário logado por trás — o poller
# automático de chamados (`server/ti/chamados.py::iniciar_poller_verificar_chamados`)
# e o webhook do GLPI (`server/ti/webhook_glpi.py`, autenticado só por
# segredo compartilhado) não têm sessão nenhuma. Único lugar que define
# essa string, pra quem chama importar em vez de cada um inventar a
# própria — usado no relatório "por usuário" da página Tokens do TI.
USUARIO_SISTEMA = "sistema"


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
        mensagens = sanitizar_mensagens(messages) if self._sanitizar else messages
        resposta = await self._cliente.chat(messages=mensagens, **kwargs)
        self._registrar_e_avisar(_texto_das_mensagens(mensagens), kwargs.get("model", ""), resposta)
        return resposta

    async def embed(self, *, input, **kwargs):
        texto = sanitizar_dado_sensivel(input) if self._sanitizar else input
        resposta = await self._cliente.embed(input=texto, **kwargs)
        self._registrar_e_avisar(texto, kwargs.get("model", ""), resposta)
        return resposta

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
        self._avisar_teto_tokens()

    def _avisar_teto_tokens(self) -> None:
        """Mesmo espírito do aviso de chamadas acima, só que por volume de
        tokens — `0`/sem configuração (`configuracoes_provedor.teto_tokens_diario`)
        significa sem teto, não avisa nunca."""
        teto = configuracoes_provedor.teto_tokens_diario()
        if teto <= 0:
            return
        tokens_hoje = auditoria_externa.tokens_hoje(self._dominio)
        if tokens_hoje > teto:
            logger.warning(
                "Domínio de IA '%s' passou do teto diário de tokens (%d > %d) — "
                "só um alerta, nada foi bloqueado.",
                self._dominio,
                tokens_hoje,
                teto,
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
        provedor = _PROVEDOR_OLLAMA_PADRAO
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
