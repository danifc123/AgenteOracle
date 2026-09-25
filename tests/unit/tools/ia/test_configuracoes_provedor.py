import contextlib

from agente_oracle.tools.ia import configuracoes_provedor as mod


class _CursorFake:
    def __init__(self, linha_fetchone=None, rowcount: int = 1):
        self._linha_fetchone = linha_fetchone
        self.rowcount = rowcount
        self.execucoes: list[tuple[str, dict]] = []

    def execute(self, sql: str, **binds):
        self.execucoes.append((sql, binds))
        return self

    def fetchone(self):
        return self._linha_fetchone


class _ConexaoFake:
    def __init__(self, cursor: _CursorFake):
        self._cursor = cursor

    def cursor(self) -> _CursorFake:
        return self._cursor


def _conexao_fake_para(monkeypatch, cursor: _CursorFake) -> None:
    @contextlib.contextmanager
    def _fake():
        yield _ConexaoFake(cursor)

    monkeypatch.setattr(mod, "get_postgres_connection", _fake)


class TestProvedorLlmAtivoId:
    def test_sem_configuracao_devolve_none(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(linha_fetchone=None))

        assert mod.provedor_llm_ativo_id() is None

    def test_devolve_o_valor_gravado_como_inteiro(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(linha_fetchone=("7",)))

        assert mod.provedor_llm_ativo_id() == 7

    def test_definir_grava_como_texto(self, monkeypatch):
        cursor = _CursorFake(rowcount=0)
        _conexao_fake_para(monkeypatch, cursor)

        mod.definir_provedor_llm_ativo_id(7)

        _sql, binds = cursor.execucoes[-1]
        assert binds["chave"] == "provedor_llm_ativo_id"
        assert binds["valor"] == "7"

    def test_definir_none_grava_vazio_e_volta_a_ler_none(self, monkeypatch):
        cursor = _CursorFake(rowcount=0)
        _conexao_fake_para(monkeypatch, cursor)

        mod.definir_provedor_llm_ativo_id(None)

        _sql, binds = cursor.execucoes[-1]
        assert binds["chave"] == "provedor_llm_ativo_id"
        assert binds["valor"] == ""


class TestTetoTokensDiario:
    def test_sem_configuracao_devolve_zero_sem_teto(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(linha_fetchone=None))

        assert mod.teto_tokens_diario() == 0

    def test_devolve_o_valor_gravado_como_inteiro(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(linha_fetchone=("50000",)))

        assert mod.teto_tokens_diario() == 50000

    def test_definir_grava_como_texto(self, monkeypatch):
        cursor = _CursorFake(rowcount=0)
        _conexao_fake_para(monkeypatch, cursor)

        mod.definir_teto_tokens_diario(50000)

        _sql, binds = cursor.execucoes[-1]
        assert binds["chave"] == "teto_tokens_diario"
        assert binds["valor"] == "50000"
