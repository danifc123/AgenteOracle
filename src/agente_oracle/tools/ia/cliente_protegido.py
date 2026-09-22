"""Client Ollama "protegido" — mesma interface de `ollama.AsyncClient`
(`chat`, `embed`), usado só na instanciação (`server/*.py`). Os agentes que
já existem (`agent/ti/qualidade_chamado.py` etc.) recebem esse client como
recebiam o de sempre e continuam chamando `.chat()`/`.embed()` exatamente
como sempre — não sabem que isso existe, então nenhum deles precisa mudar.

Intercepta toda chamada antes de sair da máquina: sanitiza (se a política
desse ponto de chamada pedir — decidida por quem instancia, não aqui) e
audita, sempre. Nenhuma IA extra no meio — sanitizar é regex, auditar é um
INSERT no Postgres local, nada de chamada de rede a mais."""

import logging

from ollama import AsyncClient

from agente_oracle.config import DominioIA, Settings, ollama_api_key_do_dominio, ollama_host_do_dominio
from agente_oracle.tools.ia import auditoria_externa
from agente_oracle.tools.ia.saneamento import sanitizar_dado_sensivel, sanitizar_mensagens

logger = logging.getLogger(__name__)


class ClienteOllamaProtegido:
    def __init__(
        self, cliente_real: AsyncClient, dominio: DominioIA, host: str, sanitizar: bool, teto_diario: int
    ):
        self._cliente = cliente_real
        self._dominio = dominio
        self._host = host
        self._sanitizar = sanitizar
        self._teto_diario = teto_diario

    async def chat(self, *, messages, **kwargs):
        mensagens = sanitizar_mensagens(messages) if self._sanitizar else messages
        self._registrar_e_avisar(_texto_das_mensagens(mensagens))
        return await self._cliente.chat(messages=mensagens, **kwargs)

    async def embed(self, *, input, **kwargs):
        texto = sanitizar_dado_sensivel(input) if self._sanitizar else input
        self._registrar_e_avisar(texto)
        return await self._cliente.embed(input=texto, **kwargs)

    def _registrar_e_avisar(self, texto: str) -> None:
        auditoria_externa.registrar(self._dominio, self._host, texto)
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


def criar_cliente_protegido(settings: Settings, dominio: DominioIA, sanitizar: bool) -> ClienteOllamaProtegido:
    """Substitui `AsyncClient(host=settings.ollama_host)` direto — resolve
    host/API key do domínio (`config.py`) e já devolve o client envolto na
    proteção. O modelo continua vindo de fora (`ollama_model_do_dominio`),
    exatamente como `settings.ollama_model` já é passado hoje pra
    `avaliar_chamado`/`classificar_categoria` — este client só cuida de
    onde a chamada vai, não de qual modelo pedir nela."""
    host = ollama_host_do_dominio(settings, dominio)
    chave = ollama_api_key_do_dominio(settings, dominio)
    cliente_real = AsyncClient(host=host, headers={"Authorization": f"Bearer {chave}"} if chave else {})
    return ClienteOllamaProtegido(cliente_real, dominio, host, sanitizar, settings.teto_diario_ia_externa)
