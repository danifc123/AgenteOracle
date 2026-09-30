"""Amostragem de chamados contra o Postgres real, simulando as 288 rodadas do poller num dia (só GLPI e IA ficam de fora)."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from agente_oracle.db.connection import get_postgres_connection
from agente_oracle.tools.ti import amostragem_chamados, configuracoes, uso_ia_chamados

pytestmark = pytest.mark.integration

_ID_BASE_TESTE = 900_000_000
_RODADAS_POR_DIA = 288  # poller de 5 em 5 minutos, 24h


def _apagar_dados_de_teste() -> None:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM ti_amostragem_chamados WHERE chamado_id >= :base", base=_ID_BASE_TESTE)
        cursor.execute("DELETE FROM ti_uso_ia_chamados WHERE chamado_id >= :base", base=_ID_BASE_TESTE)


@pytest.fixture(autouse=True)
def _isolar_dados_de_teste():
    amostragem_chamados.ids_fora_da_amostra()  # cria a tabela, se ainda não existir
    uso_ia_chamados.resumo_uso(1)
    _apagar_dados_de_teste()
    yield
    _apagar_dados_de_teste()


@pytest.fixture
def regime(monkeypatch):
    """Define em memória o percentual, a data da última mudança e a flag de antigos."""

    def _definir(percentual, desde=None, ler_antigos=False) -> None:
        monkeypatch.setattr(configuracoes, "percentual_amostragem_chamados", lambda: Decimal(str(percentual)))
        monkeypatch.setattr(configuracoes, "percentual_alterado_em", lambda: desde, raising=False)
        monkeypatch.setattr(configuracoes, "ler_chamados_antigos", lambda: ler_antigos, raising=False)

    return _definir


@pytest.fixture
def definir_percentual(regime):
    """Só o percentual (sem data de referência, flag desligada)."""
    return regime


def _simular_dia(
    id_inicial: int,
    chegadas: dict[int, int],
    rodadas: int = _RODADAS_POR_DIA,
) -> tuple[list[int], set[int]]:
    """`chegadas`: {número da rodada: quantos chamados novos chegam nela}.
    Devolve (todos os chamados que chegaram, os que foram analisados)."""
    ainda_novos: list[int] = []
    todos: list[int] = []
    analisados: set[int] = set()
    proximo_id = id_inicial
    for rodada in range(rodadas):
        for _ in range(chegadas.get(rodada, 0)):
            ainda_novos.append(proximo_id)
            todos.append(proximo_id)
            proximo_id += 1
        for chamado_id in [c for c in ainda_novos if c not in analisados]:
            if amostragem_chamados.deve_analisar(chamado_id):
                analisados.add(chamado_id)
        ainda_novos = [c for c in ainda_novos if c not in analisados]
    return todos, analisados


_UM_POR_HORA = {hora * 12: 1 for hora in range(10)}  # 10 chamados, 1 a cada 12 rodadas (1h)


class TestContagemAoLongoDoDia:
    def test_dez_chamados_ao_longo_do_dia_a_20_por_cento_analisam_so_dois(self, definir_percentual):
        definir_percentual(20)

        todos, analisados = _simular_dia(_ID_BASE_TESTE + 1000, _UM_POR_HORA)

        assert len(todos) == 10
        assert len(analisados) == 2

    def test_checar_de_novo_nao_amplia_a_amostra(self, definir_percentual):
        # O medo original: com uma checagem a cada 5 min, "no fim do dia todos
        # teriam sido analisados". Rodar mais um dia inteiro de checagens
        # sobre os MESMOS chamados não pode mudar nada.
        definir_percentual(20)
        todos, analisados = _simular_dia(_ID_BASE_TESTE + 2000, _UM_POR_HORA)

        excluidos = [c for c in todos if c not in analisados]
        reanalisados = {
            c for _ in range(_RODADAS_POR_DIA) for c in excluidos if amostragem_chamados.deve_analisar(c)
        }

        assert reanalisados == set()

    def test_percentual_quebrado_arredonda_pra_baixo_nunca_pra_cima(self, definir_percentual):
        definir_percentual("33.333")

        _todos, analisados = _simular_dia(_ID_BASE_TESTE + 3000, _UM_POR_HORA)

        assert len(analisados) == 3  # floor(10 × 33,333%) = 3, não 4

    def test_todos_os_chamados_chegando_de_uma_vez_seguem_a_mesma_conta(self, definir_percentual):
        definir_percentual(20)

        _todos, analisados = _simular_dia(_ID_BASE_TESTE + 4000, {0: 10})

        assert len(analisados) == 2

    def test_um_unico_chamado_no_dia_nao_e_analisado(self, definir_percentual):
        # Comportamento atual (contagem acumulada com floor): o 1º chamado a 20%
        # vale floor(0,2) = 0.
        definir_percentual(20)

        _todos, analisados = _simular_dia(_ID_BASE_TESTE + 5000, {100: 1})

        assert analisados == set()

    def test_cinco_chamados_no_dia_a_20_por_cento_analisam_um(self, definir_percentual):
        definir_percentual(20)

        _todos, analisados = _simular_dia(_ID_BASE_TESTE + 6000, {i * 50: 1 for i in range(5)})

        assert len(analisados) == 1

    def test_contagem_e_acumulada_entre_dias_nao_reinicia_a_meia_noite(self, definir_percentual):
        # Comportamento atual: 4 chamados por dia a 20%, dois dias seguidos.
        # Cada dia isolado daria floor(0,8) = 0; o acumulado dos dois dias é
        # floor(8 × 20%) = 1.
        definir_percentual(20)

        _dia1, analisados_dia1 = _simular_dia(_ID_BASE_TESTE + 7000, {0: 4})
        _dia2, analisados_dia2 = _simular_dia(_ID_BASE_TESTE + 7100, {0: 4})

        assert len(analisados_dia1) + len(analisados_dia2) == 1


class TestEstoqueAntigoAoLigarOPercentual:
    def test_chamados_novos_ja_existentes_contam_como_vistos_na_primeira_rodada(self, definir_percentual):
        # Comportamento atual, DECISÃO PENDENTE: 30 chamados `novo` já parados no
        # GLPI quando o 20% é ligado entram todos na conta da 1ª rodada —
        # 6 são analisados de uma vez, gastando a cota com chamado velho.
        definir_percentual(20)

        _todos, analisados = _simular_dia(_ID_BASE_TESTE + 8000, {0: 30}, rodadas=1)

        assert len(analisados) == 6


class TestMudancaDePercentual:
    def test_mudar_o_percentual_reinicia_a_contagem(self, definir_percentual):
        # Comportamento atual: só decisões tomadas sob o percentual ATUAL
        # entram na conta. 4 chamados a 20% (0 analisados) e depois 50%: se a
        # contagem continuasse, o 5º chamado entraria de imediato.
        definir_percentual(20)
        _simular_dia(_ID_BASE_TESTE + 9000, {0: 4}, rodadas=1)
        definir_percentual(50)

        primeiro = amostragem_chamados.deve_analisar(_ID_BASE_TESTE + 9100)
        segundo = amostragem_chamados.deve_analisar(_ID_BASE_TESTE + 9101)

        assert (primeiro, segundo) == (False, True)

    def test_chamado_ja_decidido_mantem_a_decisao_ao_mudar_o_percentual(self, definir_percentual):
        definir_percentual(20)
        excluido = _ID_BASE_TESTE + 9200
        assert amostragem_chamados.deve_analisar(excluido) is False

        definir_percentual(50)

        assert amostragem_chamados.deve_analisar(excluido) is False


class TestSubirPara100:
    def test_ao_subir_para_100_os_chamados_que_ficaram_de_fora_passam_a_ser_analisados(
        self, definir_percentual
    ):
        # Decisão do time: 100% é "geral" — inclui quem tinha ficado de fora.
        definir_percentual(20)
        todos, analisados = _simular_dia(_ID_BASE_TESTE + 10_000, _UM_POR_HORA)
        excluidos = [c for c in todos if c not in analisados]
        assert excluidos

        definir_percentual(100)

        assert all(amostragem_chamados.deve_analisar(c) for c in excluidos)

    def test_chamado_excluido_que_e_analisado_depois_volta_a_aparecer_na_tela(self, definir_percentual):
        # Depois de analisado, ele não pode continuar na lista "fora da
        # amostra" — a tela esconde essa lista, e o chamado (agora aguardando
        # resposta ou já com técnico) sumiria de quem precisa vê-lo.
        definir_percentual(20)
        chamado_id = _ID_BASE_TESTE + 10_500
        assert amostragem_chamados.deve_analisar(chamado_id) is False
        assert chamado_id in amostragem_chamados.ids_fora_da_amostra()

        definir_percentual(100)
        assert amostragem_chamados.deve_analisar(chamado_id) is True
        uso_ia_chamados.registrar(chamado_id, True, False, 1)  # o que o poller grava ao terminar a triagem

        assert chamado_id not in amostragem_chamados.ids_fora_da_amostra()

    def test_chamado_realmente_excluido_continua_escondido_da_tela(self, definir_percentual):
        definir_percentual(20)
        chamado_id = _ID_BASE_TESTE + 10_600
        assert amostragem_chamados.deve_analisar(chamado_id) is False

        assert chamado_id in amostragem_chamados.ids_fora_da_amostra()


class TestSimultaneidade:
    def test_vinte_chamados_decididos_ao_mesmo_tempo_analisam_exatamente_quatro(self, definir_percentual):
        # Poller e webhook rodam em threads diferentes: sem o lock, dois
        # chamados leriam a mesma contagem e entrariam (ou não) juntos.
        definir_percentual(20)
        ids = [_ID_BASE_TESTE + 11_000 + i for i in range(20)]

        with ThreadPoolExecutor(max_workers=8) as pool:
            decisoes = list(pool.map(amostragem_chamados.deve_analisar, ids))

        assert sum(decisoes) == 4

    def test_o_mesmo_chamado_em_varias_threads_tem_uma_decisao_so(self, definir_percentual):
        definir_percentual(50)
        chamado_id = _ID_BASE_TESTE + 12_000
        barreira = threading.Barrier(6)

        def decidir(_indice: int) -> bool:
            barreira.wait()
            return amostragem_chamados.deve_analisar(chamado_id)

        with ThreadPoolExecutor(max_workers=6) as pool:
            decisoes = list(pool.map(decidir, range(6)))

        assert len(set(decisoes)) == 1
        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM ti_amostragem_chamados WHERE chamado_id = :id", id=chamado_id
            )
            assert cursor.fetchone()[0] == 1


# Referência = última mudança de percentual; a flag decide o que fazer com chamado criado antes dela.


def _rodar_rodadas(chamados: dict[int, datetime], analisados: set[int], rodadas: int) -> None:
    """Cada rodada do poller: todo chamado ainda `novo` (id crescente, como o
    GLPI lista) é consultado com a data de criação real."""
    for _ in range(rodadas):
        for chamado_id in sorted(chamados):
            if chamado_id in analisados:
                continue
            if amostragem_chamados.deve_analisar(chamado_id, criado_em=chamados[chamado_id]):
                analisados.add(chamado_id)


def _chamados(id_inicial: int, quantidade: int, primeiro_criado_em: datetime) -> dict[int, datetime]:
    return {id_inicial + i: primeiro_criado_em + timedelta(minutes=i) for i in range(quantidade)}


def _cenario_20_para_50(regime, ler_antigos: bool):
    """10 chamados a 20% (2 analisados, 8 de fora) e, depois da mudança para 50%,
    chegam mais 4. Devolve (antigos, novos, analisados)."""
    agora = datetime.now(UTC)
    regime(20, desde=agora - timedelta(days=2), ler_antigos=ler_antigos)
    antigos = _chamados(_ID_BASE_TESTE + 20_000, 10, agora - timedelta(days=1))
    analisados: set[int] = set()
    _rodar_rodadas(antigos, analisados, rodadas=3)
    assert len(analisados) == 2  # ponto de partida: 8 ficaram de fora a 20%

    regime(50, desde=agora, ler_antigos=ler_antigos)
    novos = _chamados(_ID_BASE_TESTE + 20_100, 4, agora + timedelta(hours=1))
    _rodar_rodadas({**antigos, **novos}, analisados, rodadas=_RODADAS_POR_DIA)
    return antigos, novos, analisados


class TestMudancaDePercentualComFlagDesligada:
    def test_antigos_ficam_como_estao_e_so_os_novos_entram_na_conta_do_novo_percentual(self, regime):
        antigos, novos, analisados = _cenario_20_para_50(regime, ler_antigos=False)

        assert len(analisados & set(novos)) == 2  # floor(4 novos × 50%)
        assert len(analisados & set(antigos)) == 2  # os mesmos 2 de antes, nenhum antigo a mais
        assert len(analisados) == 4  # 4 de 14

    def test_os_antigos_que_ficaram_de_fora_continuam_escondidos_da_tela(self, regime):
        antigos, _novos, analisados = _cenario_20_para_50(regime, ler_antigos=False)

        excluidos = set(antigos) - analisados

        assert excluidos <= amostragem_chamados.ids_fora_da_amostra()


class TestMudancaDePercentualComFlagLigada:
    def test_antigos_entram_na_conta_e_os_ja_analisados_contam_como_parte_da_cota(self, regime):
        antigos, novos, analisados = _cenario_20_para_50(regime, ler_antigos=True)

        assert len(analisados) == 7  # floor(14 × 50%), aproveitando os 2 já feitos
        assert len(analisados & set(novos)) == 2
        assert len(analisados & set(antigos)) == 5  # os 2 de antes + 3 antigos que estavam de fora

    def test_o_antigo_e_reavaliado_uma_vez_so_e_depois_a_decisao_fica_estavel(self, regime):
        antigos, novos, analisados = _cenario_20_para_50(regime, ler_antigos=True)
        depois_de_um_dia = set(analisados)

        _rodar_rodadas({**antigos, **novos}, analisados, rodadas=_RODADAS_POR_DIA)

        assert analisados == depois_de_um_dia


class TestEstoqueParadoAoLigarOPercentual:
    def test_flag_desligada_ignora_o_estoque_antigo_e_a_cota_vai_so_pra_chamado_novo(self, regime):
        agora = datetime.now(UTC)
        regime(20, desde=agora, ler_antigos=False)
        estoque = _chamados(_ID_BASE_TESTE + 21_000, 30, agora - timedelta(days=3))
        analisados: set[int] = set()

        _rodar_rodadas(estoque, analisados, rodadas=3)

        assert analisados == set()  # nenhum dos 30 é analisado
        assert set(estoque) <= amostragem_chamados.ids_fora_da_amostra()  # e somem da tela

        novos = _chamados(_ID_BASE_TESTE + 21_100, 5, agora + timedelta(hours=1))
        _rodar_rodadas({**estoque, **novos}, analisados, rodadas=3)

        assert len(analisados) == 1  # floor(5 novos × 20%) — o estoque não gastou cota
        assert analisados <= set(novos)

    def test_flag_ligada_conta_o_estoque_antigo_na_cota(self, regime):
        agora = datetime.now(UTC)
        regime(20, desde=agora, ler_antigos=True)
        estoque = _chamados(_ID_BASE_TESTE + 22_000, 30, agora - timedelta(days=3))
        analisados: set[int] = set()

        _rodar_rodadas(estoque, analisados, rodadas=3)

        assert len(analisados) == 6  # floor(30 × 20%)

    def test_ligar_a_flag_depois_libera_o_estoque_que_tinha_sido_ignorado(self, regime):
        agora = datetime.now(UTC)
        regime(20, desde=agora, ler_antigos=False)
        estoque = _chamados(_ID_BASE_TESTE + 23_000, 30, agora - timedelta(days=3))
        analisados: set[int] = set()
        _rodar_rodadas(estoque, analisados, rodadas=3)
        assert analisados == set()

        regime(20, desde=agora, ler_antigos=True)  # mesma referência, só a flag mudou
        _rodar_rodadas(estoque, analisados, rodadas=3)

        assert len(analisados) == 6


class TestRegrasDeBorda:
    def test_em_100_por_cento_tudo_e_analisado_com_a_flag_desligada(self, regime):
        agora = datetime.now(UTC)
        regime(20, desde=agora - timedelta(days=1), ler_antigos=False)
        chamados = _chamados(_ID_BASE_TESTE + 24_000, 10, agora - timedelta(hours=5))
        analisados: set[int] = set()
        _rodar_rodadas(chamados, analisados, rodadas=3)
        assert len(analisados) == 2

        regime(100, desde=agora, ler_antigos=False)  # todos os 10 ficaram "antigos"
        _rodar_rodadas(chamados, analisados, rodadas=3)

        assert analisados == set(chamados)

    def test_sem_data_de_referencia_todos_sao_tratados_como_novos(self, regime):
        # Configuração criada antes desta funcionalidade (percentual sem data):
        # o comportamento é o de sempre, sem chamado "antigo".
        regime(20, desde=None, ler_antigos=False)
        chamados = _chamados(_ID_BASE_TESTE + 25_000, 10, datetime.now(UTC) - timedelta(days=30))
        analisados: set[int] = set()

        _rodar_rodadas(chamados, analisados, rodadas=3)

        assert len(analisados) == 2

    def test_chamado_criado_exatamente_na_data_da_mudanca_conta_como_novo(self, regime):
        agora = datetime.now(UTC)
        regime(20, desde=agora, ler_antigos=False)
        chamados = {_ID_BASE_TESTE + 26_000 + i: agora for i in range(5)}
        analisados: set[int] = set()

        _rodar_rodadas(chamados, analisados, rodadas=3)

        assert len(analisados) == 1  # se fossem "antigos" com a flag desligada, seria 0
