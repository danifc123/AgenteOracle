from dataclasses import replace
from datetime import UTC, datetime

from agente_oracle.tools.ti.glpi import (
    Chamado,
    _chamado_do_json,
    _data_do_glpi,
    _status_do_glpi,
    chamado_e_alheio,
)

_CHAMADO_TESTE = Chamado(
    id=1,
    titulo="T",
    descricao="D",
    categoria="Categoria",
    categoria_id=1,
    status="aguardando_usuario",
    solicitante="Solicitante",
    email="",
    avaliacao_mensagem=None,
    criado_em=datetime(2026, 1, 1, tzinfo=UTC),
    area=None,
    tecnico_atribuido=None,
)


class TestStatusDoGlpi:
    def test_novo_mapeia_pro_codigo_1(self):
        assert _status_do_glpi(1) == "novo"

    def test_processando_atribuido_mapeia_pra_fila_atendimento(self):
        assert _status_do_glpi(2) == "fila_atendimento"

    def test_processando_planejado_tambem_mapeia_pra_fila_atendimento(self):
        assert _status_do_glpi(3) == "fila_atendimento"

    def test_pendente_mapeia_pra_aguardando_usuario(self):
        assert _status_do_glpi(4) == "aguardando_usuario"

    def test_codigo_desconhecido_cai_pra_novo(self):
        # Solucionado/Fechado (5/6) e qualquer valor não mapeado — nunca
        # levanta erro, sempre devolve um status válido do nosso modelo.
        assert _status_do_glpi(6) == "novo"
        assert _status_do_glpi(None) == "novo"


class TestDataDoGlpi:
    def test_formato_esperado_converte_corretamente(self):
        data = _data_do_glpi("2026-03-15 10:30:00")
        assert data.year == 2026
        assert data.month == 3
        assert data.day == 15

    def test_valor_vazio_devolve_agora_em_vez_de_levantar(self):
        assert _data_do_glpi(None) is not None
        assert _data_do_glpi("") is not None

    def test_formato_inesperado_devolve_agora_em_vez_de_levantar(self):
        assert _data_do_glpi("não é uma data") is not None


class TestChamadoDoJson:
    def test_mapeia_campos_basicos(self):
        item = {
            "id": 42,
            "name": "Sistema lento",
            "content": "descrição do problema",
            "status": {"id": 1, "name": "Novo"},
            "category": {"id": 5, "name": "Sistemas"},
            "user_recipient": {"id": 3, "name": "solicitante1"},
            "date_creation": "2026-01-01T08:00:00-03:00",
            "team": [],
        }
        chamado = _chamado_do_json(item)
        assert chamado.id == 42
        assert chamado.titulo == "Sistema lento"
        assert chamado.descricao == "descrição do problema"
        assert chamado.status == "novo"
        assert chamado.categoria == "Sistemas"
        assert chamado.categoria_id == 5
        assert chamado.solicitante == "solicitante1"

    def test_categoria_nula_vira_string_vazia_e_id_none(self):
        item = {"id": 1, "name": "T", "content": "D", "status": {"id": 1}, "category": None}
        chamado = _chamado_do_json(item)
        assert chamado.categoria == ""
        assert chamado.categoria_id is None

    def test_sem_tecnico_atribuido_devolve_none(self):
        item = {"id": 1, "name": "T", "content": "D", "status": {"id": 1}, "team": []}
        assert _chamado_do_json(item).tecnico_atribuido is None

    def test_time_so_com_grupo_atribuido_devolve_none(self):
        # Atribuição só a um grupo (`type: "Group"`) não tem um único
        # técnico responsável pra virar `tecnico_atribuido`.
        item = {
            "id": 1,
            "name": "T",
            "content": "D",
            "status": {"id": 1},
            "team": [{"role": "assigned", "type": "Group", "id": 9, "name": "Cadastro"}],
        }
        assert _chamado_do_json(item).tecnico_atribuido is None

    def test_com_tecnico_atribuido_devolve_string(self):
        item = {
            "id": 1,
            "name": "T",
            "content": "D",
            "status": {"id": 1},
            "team": [{"role": "assigned", "type": "User", "id": 7, "name": "tec7"}],
        }
        assert _chamado_do_json(item).tecnico_atribuido == "7"

    def test_avaliacao_mensagem_sempre_none(self):
        # Não tem equivalente nativo no GLPI — só existe no nosso modelo.
        item = {"id": 1, "name": "T", "content": "D", "status": {"id": 1}, "team": []}
        chamado = _chamado_do_json(item)
        assert chamado.avaliacao_mensagem is None
        assert chamado.area is None


class TestChamadoEAlheio:
    def test_pendente_com_tecnico_real_e_alheio(self):
        # Combinação que o nosso próprio fluxo nunca produz — chamado
        # gerenciado fora do sistema (ex: #2530, "Aguardando fornecedor"
        # com um técnico já atribuído manualmente no GLPI).
        chamado = replace(_CHAMADO_TESTE, tecnico_atribuido="7")
        assert chamado_e_alheio(chamado, conta_ia_id="274") is True

    def test_pendente_com_conta_da_ia_nao_e_alheio(self):
        # Ainda é a IA sozinha segurando o lugar — parte normal do fluxo.
        chamado = replace(_CHAMADO_TESTE, tecnico_atribuido="274")
        assert chamado_e_alheio(chamado, conta_ia_id="274") is False

    def test_pendente_sem_ninguem_nao_e_alheio(self):
        chamado = replace(_CHAMADO_TESTE, tecnico_atribuido=None)
        assert chamado_e_alheio(chamado, conta_ia_id="274") is False

    def test_novo_com_tecnico_nao_e_alheio(self):
        # A checagem é só pra status `aguardando_usuario` — um chamado
        # `novo` com técnico atribuído é um caso diferente, fora deste
        # escopo.
        chamado = replace(_CHAMADO_TESTE, status="novo", tecnico_atribuido="7")
        assert chamado_e_alheio(chamado, conta_ia_id="274") is False

    def test_fila_atendimento_com_tecnico_nao_e_alheio(self):
        chamado = replace(_CHAMADO_TESTE, status="fila_atendimento", tecnico_atribuido="7")
        assert chamado_e_alheio(chamado, conta_ia_id="274") is False
