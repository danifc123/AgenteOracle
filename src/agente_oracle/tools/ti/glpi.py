"""Chamados de service desk (GLPI) — integração real com a API REST v2.3
do GLPI via `httpx` (`ClienteGLPIReal`, sem cliente mock — ver
`criar_cliente()`). `ClienteGLPI` é a interface que
`agent/ti/qualidade_chamado.py`, `agent/ti/roteamento_chamado.py` e
`server/ti/chamados.py` usam (`titulo`≈`name`, `descricao`≈`content` do
GLPI). GLPI 11+ dispara webhook nativo no evento "Ticket created"
(`server/ti/webhook_glpi.py`), complementando o polling manual
(`/api/ti/chamados/verificar`).

Pontos da API real que não são óbvios pelo Swagger sozinho:

- Autenticação é grant `password` (client_id/secret do client OAuth
  **mais** usuário/senha de uma conta de serviço), não
  `client_credentials` — este GLPI rejeita token de `client_credentials`
  puro (`sub` = client_id, sem usuário real) em qualquer endpoint de
  recurso. Em homologação, `GLPI_USERNAME`/`GLPI_PASSWORD` apontam pra
  uma conta compartilhada com outra integração ("api.ebarn"), só pra
  teste — produção deve usar uma conta dedicada.
- Endpoints são namespaced por módulo: `/api.php/v2.3/Assistance/Ticket`
  (não `/api.php/v2/Ticket`). Atribuir técnico é `POST
  .../Ticket/{id}/TeamMember` com `{"type": "User", "id": ...,
  "role": "assigned"}`. Comentário é `POST
  .../Ticket/{id}/Timeline/Followup` com `{"content": "..."}`.
- `status`/`category` vêm como objeto aninhado (`{"id", "name"}`), não
  campo plano.
- Data vem em ISO 8601 com fuso (`"2026-04-30T08:59:41-03:00"`).
- A lista de chamados inclui os deletados (`is_deleted: true`) —
  `listar()` filtra isso.
- Não há e-mail do solicitante no payload do Ticket — `user_recipient` só
  traz `id`/`name` (login); `Chamado.email` fica vazio no cliente real
  (buscar de verdade exigiria uma chamada extra a `/User/{id}`, fora do
  escopo desta rodada).

Ver também o TODO em `tools/ti/tecnicos.py` (formato do identificador de
técnico) e em `server/ti/webhook_glpi.py` (header/payload do webhook,
ainda não confirmados).

`reportar_usuario` é no-op de propósito nesta fase: o GLPI já notifica o
solicitante na criação do chamado; notificação de "chamado incompleto"
(e-mail/Teams) é fase seguinte, fora do escopo aqui."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Literal, Protocol

import httpx

from agente_oracle.config import Settings

StatusChamado = Literal["novo", "aguardando_usuario", "fila_atendimento"]
AreaChamado = Literal["processos", "sistemas", "infra"]

_TIMEOUT_HTTP_SEGUNDOS = 10.0
_MARGEM_EXPIRACAO_TOKEN_SEGUNDOS = 30
# `_requisicao` repete só métodos idempotentes (nunca `POST`, que cria
# recurso) quando a conexão cai no meio — ver a docstring do método.
_MAX_TENTATIVAS_HTTP = 3
_ESPERA_ENTRE_TENTATIVAS_SEGUNDOS = 1.0
_METODOS_SEGUROS_PRA_REPETIR = frozenset({"GET", "PATCH", "DELETE"})
# Só um teto de pedido — o GLPI limita a resposta a ~100 itens de
# qualquer forma (ver `ClienteGLPIReal._listar_com_filtro`).
_TAMANHO_PAGINA_SOLICITADO = 999
# Rede de segurança contra loop infinito em `_listar_com_filtro` — cobre
# a escala atual (milhares de chamados) com folga, mesmo a ~100 por
# página.
_MAX_PAGINAS_LISTAR = 50


@dataclass(frozen=True)
class Chamado:
    id: int
    titulo: str
    descricao: str
    categoria: str
    # ID real da categoria no GLPI (`tools/ti/categorias.py`) — é o que
    # `classificar_categoria` usa pra saber em qual área a categoria atual
    # já está, antes de decidir se corrige.
    categoria_id: int | None
    status: StatusChamado
    solicitante: str
    email: str
    avaliacao_mensagem: str | None
    reportado_em: datetime | None
    criado_em: datetime
    area: AreaChamado | None
    tecnico_atribuido: str | None


class ClienteGLPI(Protocol):
    async def listar(self) -> list[Chamado]: ...

    async def buscar(self, chamado_id: int) -> Chamado | None: ...

    async def atualizar_avaliacao(
        self, chamado_id: int, status: StatusChamado, mensagem: str | None
    ) -> None: ...

    async def atribuir(self, chamado_id: int, area: AreaChamado, tecnico_identificador: str) -> None: ...

    async def atualizar_categoria(self, chamado_id: int, categoria_id: int) -> None: ...

    async def carga_atual_por_tecnico(self, tecnicos_identificadores: list[str]) -> dict[str, int]: ...

    async def reportar_usuario(self, chamado_id: int) -> None: ...


# Códigos confirmados contra o schema `status` da instância real (campo
# `status.id` do Ticket, enum documentado no Swagger): 1=Novo, 10=Aprovação,
# 2=Em atendimento (atribuído), 3=Em atendimento (planejado), 4=Pendente,
# 5=Solucionado, 6=Fechado. "fila_atendimento" mapeia pra 2 (já atribuído a
# um técnico, que é exatamente quando este status é gravado — ver
# `server/ti/chamados.py::processar_chamado_novo`); 10 (Aprovação) cai no
# default "novo" do `.get()` em `_status_do_glpi`, sem mapeamento próprio
# por enquanto.
_STATUS_GLPI_PARA_NOSSO: dict[int, StatusChamado] = {
    1: "novo",
    2: "fila_atendimento",
    3: "fila_atendimento",
    4: "aguardando_usuario",
}
_STATUS_NOSSO_PARA_GLPI: dict[StatusChamado, int] = {
    "novo": 1,
    "aguardando_usuario": 4,
    "fila_atendimento": 2,
}


def _status_do_glpi(valor_bruto: object) -> StatusChamado:
    return _STATUS_GLPI_PARA_NOSSO.get(valor_bruto, "novo")  # type: ignore[arg-type]


def _filtro_rsql_por_status(nossos_status: tuple[StatusChamado, ...]) -> str:
    """Monta um filtro RSQL (`?filter=status.id==X,status.id==Y`, vírgula
    é "OU" em RSQL) a partir dos códigos GLPI que mapeiam pra algum dos
    nossos status — derivado de `_STATUS_GLPI_PARA_NOSSO` pra nunca
    duplicar a lista de códigos em dois lugares."""
    ids_glpi = [id_glpi for id_glpi, nosso in _STATUS_GLPI_PARA_NOSSO.items() if nosso in nossos_status]
    return ",".join(f"status.id=={id_glpi}" for id_glpi in ids_glpi)


# `listar()` só busca o que a tela de Auditoria acompanha (`novo`/
# `aguardando_usuario`); `carga_atual_por_tecnico` busca só
# `fila_atendimento` — cada um filtra direto no servidor (`filter=`, ver
# `_listar_com_filtro`) em vez de baixar TODO chamado da empresa (2000+)
# só pra descartar a maioria depois.
_FILTRO_NOVO_OU_PENDENTE = _filtro_rsql_por_status(("novo", "aguardando_usuario"))
_FILTRO_FILA_ATENDIMENTO = _filtro_rsql_por_status(("fila_atendimento",))

# Confirmado contra o catálogo `PendingReason` do GLPI: id=1 é "Aguardando
# usuário" (o único motivo que a IA usa — "Aguardando fornecedor" é uma
# escolha manual de quem já está atendendo, não faz sentido pra um
# chamado que a IA ainda nem triou). `_PENDING_REASON_FOLLOWUP_
# FREQUENCIA_SEGUNDOS`/`_PENDING_REASON_FOLLOWUPS_ANTES_DE_RESOLVER` são
# os valores reais configurados nesse motivo (1 dia, resolve sozinho
# depois de 3 lembretes sem resposta) — precisam ser copiados manualmente
# ao criar o vínculo (`ClienteGLPIReal._marcar_aguardando_usuario`),
# porque a API Legada não copia isso sozinha.
_PENDING_REASON_ID_AGUARDANDO_USUARIO = 1
_PENDING_REASON_FREQUENCIA_LEMBRETE_SEGUNDOS = 86400
_PENDING_REASON_LEMBRETES_ANTES_DE_RESOLVER = 3
# GLPI grava `last_bump_date` em horário local, sem fuso explícito — Brasil
# não usa horário de verão desde 2019, então -03:00 é estável o ano todo.
_FUSO_BRASIL = timezone(timedelta(hours=-3))


def _data_do_glpi(valor: str | None) -> datetime:
    """GLPI (API v2.3) devolve data em ISO 8601 com fuso — ex:
    `"2026-04-30T08:59:41-03:00"`, confirmado contra a instância real.
    `datetime.fromisoformat` já entende esse formato nativamente; "agora" é
    só o fallback nunca-falha se vier algo fora do esperado."""
    if not valor:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return datetime.now(UTC)


def _tecnico_atribuido_do_time(time: list[dict]) -> str | None:
    """`team[]` do Ticket mistura membros `type: "User"` e `type: "Group"`
    sob o mesmo `role: "assigned"` — só o primeiro usuário (pessoa) conta
    como "o técnico"; atribuição só a um grupo não tem um único
    responsável pra virar `tecnico_atribuido`."""
    for membro in time:
        if membro.get("role") == "assigned" and membro.get("type") == "User":
            return str(membro["id"])
    return None


def _nome_completo_categoria(categoria_id: int | None, nome_da_api: str) -> str:
    """A API do GLPI só devolve o nome da folha (`category.name`, ex:
    "Suporte Operacional (Cadastros, Ajustes de Parâmetros)"), mas a tela
    do GLPI mostra o caminho completo da árvore (ex: "Tecnologia da
    Informação > Sistemas de Negócio > Protheus > Suporte..."). Usa o
    caminho completo já salvo em `tools/ti/categorias.py` quando a
    categoria é conhecida, pra bater com o que a pessoa vê lá — cai pro
    nome da API se a categoria não estiver no catálogo (`buscar()`, ao
    contrário de `listar()`, não filtra só categoria de TI). Import local
    pra evitar ciclo (`categorias.py` importa `AreaChamado` daqui)."""
    if categoria_id is None:
        return nome_da_api

    from agente_oracle.tools.ti import categorias

    categoria = next((c for c in categorias.CATEGORIAS if c.id == categoria_id), None)
    return categoria.nome if categoria else nome_da_api


def _chamado_do_json(item: dict) -> Chamado:
    """Mapeamento confirmado contra a instância real (Swagger + dado de
    exemplo) — `status`/`category` vêm como objeto aninhado `{"id",
    "name"}`, não campo plano. `email` fica sempre vazio no cliente real:
    `user_recipient` só traz `id`/`name` (login), o e-mail exigiria uma
    chamada extra a `/User/{id}`, fora do escopo desta rodada.
    `avaliacao_mensagem`/`reportado_em` não têm equivalente nativo no
    GLPI — só existem no nosso modelo, ficam sempre `None` vindo de lá."""
    status = item.get("status") or {}
    categoria = item.get("category")
    categoria_id = categoria["id"] if categoria else None
    solicitante = item.get("user_recipient") or {}
    return Chamado(
        id=item["id"],
        titulo=item.get("name", ""),
        descricao=item.get("content", ""),
        categoria=_nome_completo_categoria(categoria_id, categoria["name"] if categoria else ""),
        categoria_id=categoria_id,
        status=_status_do_glpi(status.get("id")),
        solicitante=solicitante.get("name", ""),
        email="",
        avaliacao_mensagem=None,
        reportado_em=None,
        criado_em=_data_do_glpi(item.get("date_creation")),
        area=None,
        tecnico_atribuido=_tecnico_atribuido_do_time(item.get("team") or []),
    )


class ClienteGLPIReal:
    """Integração real com a API REST v2.3 do GLPI, via `httpx.AsyncClient`.
    Endpoints e formato de payload confirmados contra o Swagger da
    instância real (`/api.php/doc`) — ver bloco dedicado na docstring do
    módulo. Autenticação é grant `password` (não `client_credentials` —
    ver o mesmo bloco pro motivo)."""

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None):
        self._settings = settings
        self._http_client = http_client or httpx.AsyncClient(
            base_url=settings.glpi_base_url, timeout=_TIMEOUT_HTTP_SEGUNDOS
        )
        self._token: str | None = None
        self._token_expira_em: datetime | None = None

    async def listar(self) -> list[Chamado]:
        # Import local pra evitar ciclo (`categorias.py` importa
        # `AreaChamado` daqui).
        from agente_oracle.tools.ti import categorias

        chamados = await self._listar_com_filtro(_FILTRO_NOVO_OU_PENDENTE)

        # Só chamado de TI: uma das ~211 categorias reais
        # (`tools/ti/categorias.py`) ou sem categoria nenhuma (chamado
        # aberto por e-mail — confirmado com o responsável do GLPI que
        # esses já entram direto na fila de TI). Sem esse filtro,
        # `listar()` devolveria chamado de qualquer departamento da
        # empresa. `server/ti/chamados.py::processar_chamado_novo` trata
        # o caso sem categoria à parte.
        return [
            chamado
            for chamado in chamados
            if chamado.categoria_id is None or chamado.categoria_id in categorias.AREA_POR_CATEGORIA_ID
        ]

    async def _listar_com_filtro(self, filtro_status: str) -> list[Chamado]:
        """Confirmado contra a instância real que o header `Range` é
        ignorado — pedir `items=100-199` devolve a mesma primeira página
        de `items=0-99`, não importa o que se peça. A saída foi um filtro
        RSQL (`?filter=`, suportado pelo endpoint) por status **e** por
        `id=gt=<último id visto>` — como os resultados vêm ordenados por
        id, isso pagina de verdade usando o próprio id como cursor, sem
        depender do `Range` quebrado. Filtrar por status também evita
        baixar TODO chamado da empresa (milhares) só pra descartar quase
        tudo depois — cada chamada aqui já busca só o que interessa pra
        quem chamou (`listar()` ou `carga_atual_por_tecnico`)."""
        itens_por_id: dict[int, dict] = {}
        ultimo_id: int | None = None
        for _pagina_atual in range(_MAX_PAGINAS_LISTAR):
            filtro = filtro_status if ultimo_id is None else f"({filtro_status});id=gt={ultimo_id}"
            resposta = await self._requisicao(
                "GET",
                "/api.php/v2.3/Assistance/Ticket",
                headers={"Range": f"items=0-{_TAMANHO_PAGINA_SOLICITADO}"},
                params={"filter": filtro},
            )
            resposta.raise_for_status()
            pagina = resposta.json()
            if not pagina:
                break
            for item in pagina:
                itens_por_id[item["id"]] = item
            ultimo_id = max(item["id"] for item in pagina)

        return [_chamado_do_json(item) for item in itens_por_id.values() if not item.get("is_deleted")]

    async def buscar(self, chamado_id: int) -> Chamado | None:
        resposta = await self._requisicao("GET", f"/api.php/v2.3/Assistance/Ticket/{chamado_id}")
        if resposta.status_code == 404:
            return None
        resposta.raise_for_status()
        return _chamado_do_json(resposta.json())

    async def atualizar_avaliacao(self, chamado_id: int, status: StatusChamado, mensagem: str | None) -> None:
        # Precisa saber o status ATUAL antes de trocar — vira `previous_status`
        # do `PendingReason_Item` lá embaixo (pra onde o GLPI volta o chamado
        # se o motivo for removido). Só busca quando faz diferença: reavaliar
        # um chamado que já estava `aguardando_usuario` não teria o que salvar
        # de diferente.
        status_anterior_glpi = None
        if status == "aguardando_usuario":
            chamado_atual = await self.buscar(chamado_id)
            if chamado_atual is not None:
                status_anterior_glpi = _STATUS_NOSSO_PARA_GLPI[chamado_atual.status]

        resposta = await self._requisicao(
            "PATCH",
            f"/api.php/v2.3/Assistance/Ticket/{chamado_id}",
            json={"status": {"id": _STATUS_NOSSO_PARA_GLPI[status]}},
        )
        resposta.raise_for_status()
        if mensagem:
            resposta_comentario = await self._requisicao(
                "POST",
                f"/api.php/v2.3/Assistance/Ticket/{chamado_id}/Timeline/Followup",
                json={"content": mensagem},
            )
            resposta_comentario.raise_for_status()

        if status == "aguardando_usuario":
            await self._marcar_aguardando_usuario(chamado_id, status_anterior_glpi)

    async def _marcar_aguardando_usuario(self, chamado_id: int, status_anterior_glpi: int | None) -> None:
        """A API v2.3 só **lê** o motivo de pendência (`GET .../Ticket/{id}/
        PendingReason`) — não existe rota de escrita nela, confirmado no
        código-fonte do GLPI (`ITILController.php`: só a rota GET foi
        implementada pra vincular um motivo a um item). Marcar "Aguardando
        usuário" de verdade só é possível pela API Legada (`apirest.php`),
        que autentica por sessão (`App-Token` + token de usuário) em vez de
        OAuth — por isso as chamadas abaixo usam `self._http_client`
        direto, sem passar por `_requisicao` (que injetaria o Bearer OAuth,
        que essa API não entende).

        Opcional: sem `glpi_legacy_api_url` configurada, não faz nada — o
        chamado já foi marcado "Pendente" (status genérico) pelo PATCH em
        `atualizar_avaliacao`, só não ganha o motivo específico.

        Idempotente: se o chamado já tiver um `PendingReason_Item` (ex:
        reavaliação de um chamado que já estava `aguardando_usuario`), não
        cria outro."""
        if not self._settings.glpi_legacy_api_url:
            return

        ja_tem_motivo = await self._requisicao(
            "GET", f"/api.php/v2.3/Assistance/Ticket/{chamado_id}/PendingReason"
        )
        if ja_tem_motivo.status_code == 200:
            return

        base = self._settings.glpi_legacy_api_url
        resposta_sessao = await self._http_client.get(
            f"{base}/initSession",
            headers={
                "App-Token": self._settings.glpi_legacy_app_token,
                "Authorization": f"user_token {self._settings.glpi_legacy_user_token}",
            },
        )
        resposta_sessao.raise_for_status()
        cabecalhos = {
            "App-Token": self._settings.glpi_legacy_app_token,
            "Session-Token": resposta_sessao.json()["session_token"],
        }
        try:
            resposta_criacao = await self._http_client.post(
                f"{base}/PendingReason_Item",
                headers=cabecalhos,
                json={
                    "input": {
                        "itemtype": "Ticket",
                        "items_id": chamado_id,
                        "pendingreasons_id": _PENDING_REASON_ID_AGUARDANDO_USUARIO,
                        "followup_frequency": _PENDING_REASON_FREQUENCIA_LEMBRETE_SEGUNDOS,
                        "followups_before_resolution": _PENDING_REASON_LEMBRETES_ANTES_DE_RESOLVER,
                        "previous_status": status_anterior_glpi,
                        # Sem isso preenchido, a tela do chamado no GLPI
                        # quebra ("Ocorreu um erro inesperado") — descoberto
                        # comparando com um vínculo real, criado pela tela,
                        # que sempre tem essa data preenchida.
                        "last_bump_date": datetime.now(_FUSO_BRASIL).strftime("%Y-%m-%d %H:%M:%S"),
                    }
                },
            )
            resposta_criacao.raise_for_status()
        finally:
            await self._http_client.get(f"{base}/killSession", headers=cabecalhos)

    async def atribuir(self, chamado_id: int, area: AreaChamado, tecnico_identificador: str) -> None:
        # `area` não tem onde ir no payload de TeamMember — se a instância
        # real usa um Group pra rotear por área, esse é o lugar de
        # adicionar uma segunda chamada aqui (role "assigned", type
        # "Group") quando isso for confirmado.
        resposta = await self._requisicao(
            "POST",
            f"/api.php/v2.3/Assistance/Ticket/{chamado_id}/TeamMember",
            json={"type": "User", "id": int(tecnico_identificador), "role": "assigned"},
        )
        resposta.raise_for_status()

    async def atualizar_categoria(self, chamado_id: int, categoria_id: int) -> None:
        """`categoria_id` vem sempre de `tools/ti/categorias.py`
        (`CategoriaGlpi.id`) — nunca inventado, é o id real de uma
        categoria que já existe no GLPI."""
        resposta = await self._requisicao(
            "PATCH",
            f"/api.php/v2.3/Assistance/Ticket/{chamado_id}",
            json={"category": {"id": categoria_id}},
        )
        resposta.raise_for_status()

    async def carga_atual_por_tecnico(self, tecnicos_identificadores: list[str]) -> dict[str, int]:
        # Busca só chamado em `fila_atendimento` direto no servidor (ver
        # `_listar_com_filtro`) — não reaproveita `listar()` porque esse
        # só busca `novo`/`aguardando_usuario` (o que a tela de Auditoria
        # acompanha), nunca `fila_atendimento`.
        chamados = await self._listar_com_filtro(_FILTRO_FILA_ATENDIMENTO)
        cargas = dict.fromkeys(tecnicos_identificadores, 0)
        for chamado in chamados:
            if chamado.tecnico_atribuido in cargas:
                cargas[chamado.tecnico_atribuido] += 1
        return cargas

    async def reportar_usuario(self, chamado_id: int) -> None:
        """No-op de propósito nesta fase — o GLPI já notifica o solicitante
        na criação do chamado; notificação de "chamado incompleto" fica
        pra fase seguinte (e-mail/Teams), fora do escopo desta integração."""
        return

    async def _requisicao(self, metodo: str, caminho: str, **kwargs) -> httpx.Response:
        """Repete `GET`/`PATCH`/`DELETE` até `_MAX_TENTATIVAS_HTTP` vezes se
        a conexão cair no meio (confirmado contra a instância real: a rede
        interna tem instabilidade ocasional, já vimos `httpx.ReadError` no
        meio de uma resposta mais de uma vez). `POST` fica de fora de
        propósito — cria recurso (Followup, TeamMember, categoria); se a
        escrita já tiver sido processada no servidor e só a resposta não
        tiver chegado, repetir criaria duplicata."""
        token = await self._token_valido()
        cabecalhos = {"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}
        if metodo not in _METODOS_SEGUROS_PRA_REPETIR:
            return await self._http_client.request(metodo, caminho, headers=cabecalhos, **kwargs)

        for tentativa in range(1, _MAX_TENTATIVAS_HTTP + 1):
            try:
                return await self._http_client.request(metodo, caminho, headers=cabecalhos, **kwargs)
            except httpx.TransportError:
                if tentativa == _MAX_TENTATIVAS_HTTP:
                    raise
                await asyncio.sleep(_ESPERA_ENTRE_TENTATIVAS_SEGUNDOS * tentativa)
        raise AssertionError("inalcançável — o loop sempre retorna ou levanta na última tentativa")

    async def _token_valido(self) -> str:
        agora = datetime.now(UTC)
        if self._token is not None and self._token_expira_em is not None and agora < self._token_expira_em:
            return self._token

        # Grant `password` (confirmado contra a instância real — ver
        # docstring do módulo pro motivo de não ser `client_credentials`),
        # endpoint e formato de resposta ({"access_token", "expires_in"})
        # também confirmados em /api.php/token.
        resposta = await self._http_client.post(
            "/api.php/token",
            data={
                "grant_type": "password",
                "client_id": self._settings.glpi_client_id,
                "client_secret": self._settings.glpi_client_secret,
                "username": self._settings.glpi_username,
                "password": self._settings.glpi_password,
                "scope": "api user email",
            },
        )
        resposta.raise_for_status()
        corpo = resposta.json()
        self._token = corpo["access_token"]
        expira_em_segundos = corpo.get("expires_in", 3600)
        self._token_expira_em = agora + timedelta(
            seconds=max(expira_em_segundos - _MARGEM_EXPIRACAO_TOKEN_SEGUNDOS, 0)
        )
        return self._token


def criar_cliente(settings: Settings) -> ClienteGLPI:
    """Sempre `ClienteGLPIReal` — não existe mais fallback mock. Sem
    `GLPI_BASE_URL`/credenciais configuradas, o servidor ainda sobe normal
    (mesmo espírito de `protheus_configurado()` em `db/connection.py`: um
    módulo sem credencial não deveria travar o resto do sistema pros
    outros times); só a própria funcionalidade de TI falha quando alguém
    de fato chama a API do GLPI sem isso configurado.

    `server/ti/chamados.py` e `server/ti/webhook_glpi.py` chamam essa
    fábrica cada um pro seu próprio `_cliente` — dois clientes reais
    independentes (cada um com seu cache de token e pool HTTP) em vez de
    compartilhar uma instância entre módulos, pra não precisar importar uma
    variável privada de um módulo dentro do outro."""
    return ClienteGLPIReal(settings)
