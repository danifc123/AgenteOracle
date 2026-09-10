import json
from unittest.mock import AsyncMock

import httpx
import pytest

from agente_oracle.config import Settings
from agente_oracle.tools.ti.glpi import ClienteGLPIReal

_BASE_URL = "https://glpi.teste.local"
# `listar()` só aceita chamado com categoria reconhecida como TI (ver
# `tools/ti/categorias.py`) — troca o catálogo real de 211 categorias por
# 1 categoria fake, pra este teste não depender de qual id real existe.
_CATEGORIA_ID_TESTE = 999


@pytest.fixture(autouse=True)
def _categoria_ti_fake(monkeypatch):
    monkeypatch.setattr(
        "agente_oracle.tools.ti.categorias.AREA_POR_CATEGORIA_ID", {_CATEGORIA_ID_TESTE: "infra"}
    )


def _settings_teste(com_api_legada: bool = False) -> Settings:
    return Settings(
        glpi_base_url=_BASE_URL,
        glpi_client_id="id-teste",
        glpi_client_secret="segredo-teste",
        glpi_username="usuario-teste",
        glpi_password="senha-teste",
        glpi_legacy_api_url=f"{_BASE_URL}/legacy" if com_api_legada else "",
        glpi_legacy_app_token="app-token-teste",
        glpi_legacy_user_token="user-token-teste",
    )


class _GlpiApiFake:
    """Simula só o suficiente da API do GLPI (via `httpx.MockTransport`)
    pra exercitar `ClienteGLPIReal` sem precisar de rede real. Endpoints e
    formato de payload aqui batem com o que foi confirmado contra o
    Swagger da instância real (ver docstring de `tools/ti/glpi.py`) —
    incluindo a paginação por filtro RSQL + cursor de id
    (`_listar_com_filtro`), já que confirmamos que o `Range` pedido por
    header é simplesmente ignorado pela instância real (sempre devolve a
    mesma primeira página, não importa o que se peça)."""

    def __init__(self):
        self.chamadas_token = 0
        self.tamanho_pagina = 1000  # grande o bastante pra devolver tudo numa página só, por padrão
        # Estado do motivo de pendência (API Legada) — ver
        # `_marcar_aguardando_usuario`. `tem_pending_reason` simula o
        # chamado já ter um motivo vinculado (caminho idempotente).
        self.tem_pending_reason = False
        self.pending_reason_items_criados: list[dict] = []
        self.sessoes_legadas_abertas = 0
        self.sessoes_legadas_fechadas = 0
        # Simula queda de conexão transitória (ver `_requisicao`) — chave
        # "METODO caminho", valor = quantas vezes ainda deve falhar antes
        # de deixar a rota responder normalmente.
        self.falhas_transitorias_restantes: dict[str, int] = {}
        self.tentativas_por_rota: dict[str, int] = {}
        # Formato confirmado ao vivo contra a instância real: uma lista de
        # `{"type": "Followup", "item": {...}}`, não um objeto plano.
        self.followups: list[dict] = []
        self.team_members_removidos: list[dict] = []
        self.tickets: list[dict] = [
            {
                "id": 1,
                "name": "Chamado 1",
                "content": "Descrição 1",
                "status": {"id": 1, "name": "Novo"},
                "category": {"id": _CATEGORIA_ID_TESTE, "name": "Categoria Teste"},
                "user_recipient": {"id": 5, "name": "solicitante1"},
                "date_creation": "2026-01-01T08:00:00-03:00",
                "is_deleted": False,
                "team": [],
            }
        ]

    def handler(self, request: httpx.Request) -> httpx.Response:
        caminho = request.url.path
        metodo = request.method

        chave = f"{metodo} {caminho}"
        self.tentativas_por_rota[chave] = self.tentativas_por_rota.get(chave, 0) + 1
        if self.falhas_transitorias_restantes.get(chave, 0) > 0:
            self.falhas_transitorias_restantes[chave] -= 1
            raise httpx.ReadError("conexão caiu (simulado)")

        if caminho == "/api.php/token" and metodo == "POST":
            self.chamadas_token += 1
            return httpx.Response(200, json={"access_token": "token-fake", "expires_in": 3600})
        if caminho == "/api.php/v2.3/Assistance/Ticket" and metodo == "GET":
            return self._pagina_de_tickets(request)
        if caminho == "/api.php/v2.3/Assistance/Ticket/1" and metodo == "GET":
            return httpx.Response(200, json=self.tickets[0])
        if caminho == "/api.php/v2.3/Assistance/Ticket/999" and metodo == "GET":
            return httpx.Response(404, json={"erro": "não encontrado"})
        if caminho == "/api.php/v2.3/Assistance/Ticket/1" and metodo == "PATCH":
            return httpx.Response(200, json={"ok": True})
        if caminho == "/api.php/v2.3/Assistance/Ticket/1/Timeline/Followup" and metodo == "POST":
            return httpx.Response(201, json={"id": 1})
        if caminho == "/api.php/v2.3/Assistance/Ticket/1/Timeline/Followup" and metodo == "GET":
            return httpx.Response(200, json=self.followups)
        if caminho == "/api.php/v2.3/Assistance/Ticket/1/TeamMember" and metodo == "POST":
            return httpx.Response(201, json={"id": 1})
        if caminho == "/api.php/v2.3/Assistance/Ticket/1/TeamMember" and metodo == "DELETE":
            self.team_members_removidos.append(json.loads(request.read()))
            return httpx.Response(200, json=None)
        if caminho == "/api.php/v2.3/Assistance/Ticket/1/PendingReason" and metodo == "GET":
            if self.tem_pending_reason:
                return httpx.Response(200, json={"id": 1, "itemtype": "Ticket", "items_id": 1})
            return httpx.Response(404, json={"status": "ERROR_ITEM_NOT_FOUND"})
        if caminho == "/legacy/initSession" and metodo == "GET":
            self.sessoes_legadas_abertas += 1
            return httpx.Response(200, json={"session_token": "sessao-legada-fake"})
        if caminho == "/legacy/PendingReason_Item" and metodo == "POST":
            self.pending_reason_items_criados.append(json.loads(request.read())["input"])
            return httpx.Response(201, json={"id": 1, "message": "Item adicionado com sucesso"})
        if caminho == "/legacy/killSession" and metodo == "GET":
            self.sessoes_legadas_fechadas += 1
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"erro": f"rota não simulada nesta suíte: {metodo} {caminho}"})

    def _pagina_de_tickets(self, request: httpx.Request) -> httpx.Response:
        # `Range` é ignorado de propósito (mesmo comportamento confirmado
        # na instância real) — só o filtro RSQL (`status.id==X`, `id=gt=Y`)
        # decide o que volta, exatamente como `_listar_com_filtro` espera.
        status_ids, cursor_id = self._parse_filtro(request.url.params.get("filter"))
        candidatos = [
            ticket
            for ticket in self.tickets
            if (status_ids is None or (ticket.get("status") or {}).get("id") in status_ids)
            and (cursor_id is None or ticket["id"] > cursor_id)
        ]
        candidatos.sort(key=lambda ticket: ticket["id"])
        pagina = candidatos[: self.tamanho_pagina]
        return httpx.Response(200, json=pagina)

    @staticmethod
    def _parse_filtro(filtro: str | None) -> tuple[set[int] | None, int | None]:
        if not filtro:
            return None, None
        status_ids: set[int] | None = None
        cursor_id: int | None = None
        for parte_bruta in filtro.split(";"):
            parte = parte_bruta.strip("()")
            if parte.startswith("id=gt="):
                cursor_id = int(parte.removeprefix("id=gt="))
            elif "status.id==" in parte:
                status_ids = {int(item.split("==", 1)[1]) for item in parte.split(",")}
        return status_ids, cursor_id


def _cliente_fake(fake: _GlpiApiFake, com_api_legada: bool = False) -> ClienteGLPIReal:
    transporte = httpx.MockTransport(fake.handler)
    http_client = httpx.AsyncClient(base_url=_BASE_URL, transport=transporte)
    return ClienteGLPIReal(_settings_teste(com_api_legada), http_client=http_client)


class TestTokenCache:
    async def test_token_e_reutilizado_entre_duas_chamadas(self):
        fake = _GlpiApiFake()
        cliente = _cliente_fake(fake)

        await cliente.listar()
        await cliente.listar()

        assert fake.chamadas_token == 1


class TestRetryHttp:
    @pytest.fixture(autouse=True)
    def _sem_espera_de_verdade(self, monkeypatch):
        # Não precisa esperar de verdade entre tentativas só pra testar
        # que elas acontecem.
        monkeypatch.setattr("agente_oracle.tools.ti.glpi.asyncio.sleep", AsyncMock())

    async def test_get_repete_apos_erro_transitorio_e_completa(self):
        fake = _GlpiApiFake()
        fake.falhas_transitorias_restantes["GET /api.php/v2.3/Assistance/Ticket/1"] = 1
        cliente = _cliente_fake(fake)

        chamado = await cliente.buscar(1)

        assert chamado is not None
        assert chamado.id == 1
        assert fake.tentativas_por_rota["GET /api.php/v2.3/Assistance/Ticket/1"] == 2

    async def test_get_desiste_apos_esgotar_tentativas(self):
        fake = _GlpiApiFake()
        fake.falhas_transitorias_restantes["GET /api.php/v2.3/Assistance/Ticket/1"] = 99
        cliente = _cliente_fake(fake)

        with pytest.raises(httpx.TransportError):
            await cliente.buscar(1)

        assert fake.tentativas_por_rota["GET /api.php/v2.3/Assistance/Ticket/1"] == 3

    async def test_post_nao_repete_mesmo_apos_erro_transitorio(self):
        # POST cria recurso (TeamMember) — repetir arriscaria duplicar uma
        # atribuição que já tenha sido processada no servidor.
        fake = _GlpiApiFake()
        fake.falhas_transitorias_restantes["POST /api.php/v2.3/Assistance/Ticket/1/TeamMember"] = 1
        cliente = _cliente_fake(fake)

        with pytest.raises(httpx.TransportError):
            await cliente.atribuir(1, "infra", "7")

        assert fake.tentativas_por_rota["POST /api.php/v2.3/Assistance/Ticket/1/TeamMember"] == 1


class TestListarEBuscar:
    async def test_listar_devolve_chamados_mapeados(self):
        cliente = _cliente_fake(_GlpiApiFake())
        chamados = await cliente.listar()
        assert len(chamados) == 1
        assert chamados[0].titulo == "Chamado 1"
        assert chamados[0].status == "novo"
        assert chamados[0].solicitante == "solicitante1"

    async def test_listar_ignora_chamados_deletados(self):
        fake = _GlpiApiFake()
        fake.tickets.append({**fake.tickets[0], "id": 2, "is_deleted": True})
        cliente = _cliente_fake(fake)

        chamados = await cliente.listar()

        assert [c.id for c in chamados] == [1]

    async def test_buscar_existente_devolve_chamado(self):
        cliente = _cliente_fake(_GlpiApiFake())
        chamado = await cliente.buscar(1)
        assert chamado is not None
        assert chamado.id == 1

    async def test_buscar_inexistente_devolve_none(self):
        cliente = _cliente_fake(_GlpiApiFake())
        assert await cliente.buscar(999) is None


class TestListarPaginacao:
    async def test_listar_junta_varias_paginas_via_cursor_de_id(self):
        # Simula o servidor limitando cada resposta a 1 item por vez — o
        # `Range` pedido não importa (é ignorado na instância real), quem
        # avança de verdade é o filtro `id=gt=<ultimo id visto>`.
        fake = _GlpiApiFake()
        fake.tamanho_pagina = 1
        fake.tickets = [{**fake.tickets[0], "id": i} for i in (1, 2, 3)]
        cliente = _cliente_fake(fake)

        chamados = await cliente.listar()

        assert sorted(chamado.id for chamado in chamados) == [1, 2, 3]

    async def test_listar_devolve_vazio_quando_nao_ha_chamados(self):
        fake = _GlpiApiFake()
        fake.tickets = []
        cliente = _cliente_fake(fake)

        assert await cliente.listar() == []


class TestListarFiltraSoTi:
    async def test_exclui_chamado_de_categoria_desconhecida(self):
        # Categoria de outro departamento (não está no catálogo de TI) —
        # não é "de TI" só porque veio do mesmo endpoint de Ticket.
        fake = _GlpiApiFake()
        fake.tickets.append(
            {**fake.tickets[0], "id": 2, "category": {"id": 111111, "name": "Categoria de Outro Depto"}}
        )
        cliente = _cliente_fake(fake)

        chamados = await cliente.listar()

        assert [chamado.id for chamado in chamados] == [1]

    async def test_inclui_chamado_sem_categoria_nenhuma(self):
        # Chamado aberto por e-mail entra sem categoria e ainda assim é de
        # TI (confirmado com o responsável do GLPI) — `listar()` inclui,
        # quem decide o que fazer com ele é `processar_chamado_novo`.
        fake = _GlpiApiFake()
        fake.tickets.append({**fake.tickets[0], "id": 2, "category": None})
        cliente = _cliente_fake(fake)

        chamados = await cliente.listar()

        assert sorted(chamado.id for chamado in chamados) == [1, 2]


class TestAtualizarAvaliacao:
    async def test_sem_mensagem_nao_levanta(self):
        cliente = _cliente_fake(_GlpiApiFake())
        await cliente.atualizar_avaliacao(1, "fila_atendimento", None)

    async def test_com_mensagem_tambem_nao_levanta(self):
        # Manda o PATCH de status e o POST de Followup — os dois
        # simulados no fake, nenhum dos dois deveria levantar.
        cliente = _cliente_fake(_GlpiApiFake())
        await cliente.atualizar_avaliacao(1, "aguardando_usuario", "Qual sistema está afetado?")

    async def test_aguardando_usuario_sem_api_legada_configurada_nao_tenta_nada(self):
        # Sem `glpi_legacy_api_url`, nem tenta abrir sessão na API Legada —
        # `com_api_legada=False` (padrão) já deixa isso vazio.
        fake = _GlpiApiFake()
        cliente = _cliente_fake(fake)

        await cliente.atualizar_avaliacao(1, "aguardando_usuario", "Qual sistema está afetado?")

        assert fake.sessoes_legadas_abertas == 0
        assert fake.pending_reason_items_criados == []

    async def test_aguardando_usuario_com_api_legada_cria_o_motivo_de_pendencia(self):
        fake = _GlpiApiFake()
        cliente = _cliente_fake(fake, com_api_legada=True)

        await cliente.atualizar_avaliacao(1, "aguardando_usuario", "Qual sistema está afetado?")

        assert fake.sessoes_legadas_abertas == 1
        assert fake.sessoes_legadas_fechadas == 1
        assert len(fake.pending_reason_items_criados) == 1
        criado = fake.pending_reason_items_criados[0]
        assert criado["itemtype"] == "Ticket"
        assert criado["items_id"] == 1
        assert criado["pendingreasons_id"] == 1
        assert criado["followup_frequency"] == 86400
        assert criado["followups_before_resolution"] == 3
        # Ticket 1 (fake) está "novo" (status.id=1) antes da troca.
        assert criado["previous_status"] == 1
        assert criado["last_bump_date"]  # preenchido — sem isso, a tela do GLPI quebra

    async def test_aguardando_usuario_com_motivo_ja_existente_nao_cria_outro(self):
        # Idempotente: reavaliar um chamado que já está `aguardando_usuario`
        # (já tem um PendingReason_Item) não deveria criar um segundo.
        fake = _GlpiApiFake()
        fake.tem_pending_reason = True
        cliente = _cliente_fake(fake, com_api_legada=True)

        await cliente.atualizar_avaliacao(1, "aguardando_usuario", "Ainda falta informação.")

        assert fake.sessoes_legadas_abertas == 0
        assert fake.pending_reason_items_criados == []


class TestAtribuir:
    async def test_nao_levanta(self):
        cliente = _cliente_fake(_GlpiApiFake())
        await cliente.atribuir(1, "infra", "7")


class TestAtribuirDesatribuirUsuario:
    async def test_atribuir_usuario_nao_levanta(self):
        # Mesmo endpoint de `atribuir()`, só sem o campo `area` (que já
        # não ia pro payload mesmo) — usado pra atribuir a conta da IA.
        cliente = _cliente_fake(_GlpiApiFake())
        await cliente.atribuir_usuario(1, "274")

    async def test_desatribuir_usuario_manda_delete_com_o_corpo_certo(self):
        # Rota confirmada na fonte do GLPI (ITILController::removeTeamMember)
        # e testada ao vivo — mesmo caminho do POST, método DELETE.
        fake = _GlpiApiFake()
        cliente = _cliente_fake(fake)

        await cliente.desatribuir_usuario(1, "274")

        assert fake.team_members_removidos == [{"type": "User", "id": 274, "role": "assigned"}]


class TestCargaAtualPorTecnico:
    async def test_conta_so_chamados_em_fila_atendimento_por_tecnico(self):
        # id=3 é "novo" (não fila_atendimento) — nem chega a voltar da
        # API, já que `carga_atual_por_tecnico` filtra por status direto
        # no servidor (`_FILTRO_FILA_ATENDIMENTO`).
        fake = _GlpiApiFake()
        fake.tickets = [
            {
                "id": 1,
                "name": "T1",
                "content": "D",
                "status": {"id": 2, "name": "Em atendimento (atribuído)"},
                "category": {"id": _CATEGORIA_ID_TESTE, "name": "Categoria Teste"},
                "user_recipient": {"id": 5, "name": "solicitante1"},
                "date_creation": "2026-01-01T08:00:00-03:00",
                "is_deleted": False,
                "team": [{"role": "assigned", "type": "User", "id": 7, "name": "tec7"}],
            },
            {
                "id": 2,
                "name": "T2",
                "content": "D",
                "status": {"id": 2, "name": "Em atendimento (atribuído)"},
                "category": {"id": _CATEGORIA_ID_TESTE, "name": "Categoria Teste"},
                "user_recipient": {"id": 5, "name": "solicitante1"},
                "date_creation": "2026-01-01T08:00:00-03:00",
                "is_deleted": False,
                "team": [{"role": "assigned", "type": "User", "id": 7, "name": "tec7"}],
            },
            {
                "id": 3,
                "name": "T3",
                "content": "D",
                "status": {"id": 1, "name": "Novo"},
                "category": {"id": _CATEGORIA_ID_TESTE, "name": "Categoria Teste"},
                "user_recipient": {"id": 5, "name": "solicitante1"},
                "date_creation": "2026-01-01T08:00:00-03:00",
                "is_deleted": False,
                "team": [{"role": "assigned", "type": "User", "id": 8, "name": "tec8"}],
            },
        ]
        cliente = _cliente_fake(fake)

        cargas = await cliente.carga_atual_por_tecnico(["7", "8"])

        assert cargas == {"7": 2, "8": 0}


class TestAtualizarCategoria:
    async def test_nao_levanta(self):
        # Mesmo endpoint/método do PATCH de status (já simulado no fake) —
        # só o corpo muda (`category` em vez de `status`).
        cliente = _cliente_fake(_GlpiApiFake())
        await cliente.atualizar_categoria(1, 175)


class TestBuscarFollowups:
    async def test_mapeia_formato_confirmado_contra_a_instancia_real(self):
        # Formato exato confirmado via `GET /Ticket/3262/Timeline/Followup`
        # contra o GLPI real (não é um objeto plano como `Ticket`).
        fake = _GlpiApiFake()
        fake.followups = [
            {
                "type": "Followup",
                "item": {
                    "id": 5254,
                    "itemtype": "Ticket",
                    "items_id": 1,
                    "content": "Qual é a mensagem de erro?",
                    "is_private": False,
                    "date": "2026-09-04T15:48:05-03:00",
                    "date_creation": "2026-09-04T15:48:05-03:00",
                    "date_mod": "2026-09-04T15:48:05-03:00",
                    "user": {"id": 274, "name": "api.ebarn"},
                },
            }
        ]
        cliente = _cliente_fake(fake)

        followups = await cliente.buscar_followups(1)

        assert len(followups) == 1
        assert followups[0].autor_id == 274
        assert followups[0].autor_nome == "api.ebarn"
        assert followups[0].conteudo == "Qual é a mensagem de erro?"

    async def test_devolve_vazio_sem_followup_nenhum(self):
        cliente = _cliente_fake(_GlpiApiFake())
        assert await cliente.buscar_followups(1) == []

    async def test_ordena_por_data_de_criacao(self):
        fake = _GlpiApiFake()
        fake.followups = [
            {
                "type": "Followup",
                "item": {
                    "content": "segundo",
                    "date_creation": "2026-09-05T00:00:00-03:00",
                    "user": {"id": 1, "name": "a"},
                },
            },
            {
                "type": "Followup",
                "item": {
                    "content": "primeiro",
                    "date_creation": "2026-09-04T00:00:00-03:00",
                    "user": {"id": 1, "name": "a"},
                },
            },
        ]
        cliente = _cliente_fake(fake)

        followups = await cliente.buscar_followups(1)

        assert [f.conteudo for f in followups] == ["primeiro", "segundo"]
