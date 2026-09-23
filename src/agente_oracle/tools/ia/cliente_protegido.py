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
`ClienteOpenAICompativel` (OCI Generative AI) — a escolha ativa é lida do
Postgres a cada chamada
(`tools/ia/configuracoes_provedor.py::provedor_ia`), não em cache, então
troca sem precisar reiniciar o servidor. Essa escolha é ÚNICA pro processo
inteiro (não por domínio) — hoje vale pra TI e RH (editável pela tela de
Configurações do TI); Financeiro/Auditoria ainda não estão ligados nisso —
tocam dado real do Oracle, protegidos por
`config.py::validar_ollama_host_seguro` até o fornecedor ser validado pra
esse tipo de dado."""

import logging

from ollama import AsyncClient
from openai import AsyncOpenAI

from agente_oracle.config import (
    MODELOS_OCI_GENERATIVE_AI,
    DominioIA,
    ProvedorIA,
    Settings,
    ollama_api_key_do_dominio,
    ollama_host_do_dominio,
    ollama_model_do_dominio,
)
from agente_oracle.tools.ia import auditoria_externa, configuracoes_provedor
from agente_oracle.tools.ia.cliente_openai_compativel import ClienteOpenAICompativel
from agente_oracle.tools.ia.saneamento import sanitizar_dado_sensivel, sanitizar_mensagens

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
        provedor: ProvedorIA,
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


def criar_cliente_protegido(
    settings: Settings, dominio: DominioIA, sanitizar: bool, usuario_id: str
) -> ClienteIAProtegido:
    """Substitui `AsyncClient(host=settings.ollama_host)` direto — olha o
    provedor ativo (`configuracoes_provedor.provedor_ia()`) e monta o
    client real certo (Ollama ou OCI), já envolto na proteção. O modelo
    continua vindo de fora (`modelo_ia_ativo`), exatamente como já era
    passado hoje pra `avaliar_chamado`/`classificar_categoria` — este
    client só cuida de onde a chamada vai, não de qual modelo pedir nela.
    `usuario_id` é `usuario["sub"]` de quem chamou, ou `USUARIO_SISTEMA`
    quando não tem sessão por trás (poller, webhook do GLPI) — vai pro
    relatório "por usuário" da página Tokens do TI."""
    provedor = configuracoes_provedor.provedor_ia()
    if provedor == "oci_openai":
        cliente_real = ClienteOpenAICompativel(
            AsyncOpenAI(
                base_url=settings.oci_openai_base_url,
                api_key=settings.oci_openai_api_key,
                project=settings.oci_openai_project_id,
            )
        )
        host = settings.oci_openai_base_url
    else:
        host = ollama_host_do_dominio(settings, dominio)
        chave = ollama_api_key_do_dominio(settings, dominio)
        cliente_real = AsyncClient(host=host, headers={"Authorization": f"Bearer {chave}"} if chave else {})
    return ClienteIAProtegido(
        cliente_real, dominio, host, sanitizar, settings.teto_diario_ia_externa, provedor, usuario_id
    )


def modelo_ia_ativo(settings: Settings, dominio: DominioIA) -> str:
    """O modelo configurado na tela (`configuracoes_provedor.modelo_ia()`),
    se alguém escolheu um; vazio cai no padrão do provedor ativo — o de
    sempre pro Ollama, o primeiro da lista fixa (`gpt-oss-120b`) pra OCI."""
    escolhido = configuracoes_provedor.modelo_ia()
    if escolhido:
        return escolhido
    if configuracoes_provedor.provedor_ia() == "oci_openai":
        return MODELOS_OCI_GENERATIVE_AI[0]
    return ollama_model_do_dominio(settings, dominio)
