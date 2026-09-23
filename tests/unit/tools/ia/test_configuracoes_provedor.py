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


class TestModeloIa:
    def test_sem_configuracao_devolve_vazio(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(linha_fetchone=None))

        assert mod.modelo_ia() == ""

    def test_devolve_o_valor_gravado(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(linha_fetchone=("openai.gpt-oss-120b",)))

        assert mod.modelo_ia() == "openai.gpt-oss-120b"

    def test_definir_grava_como_texto(self, monkeypatch):
        cursor = _CursorFake(rowcount=0)
        _conexao_fake_para(monkeypatch, cursor)

        mod.definir_modelo_ia("openai.gpt-oss-120b")

        _sql, binds = cursor.execucoes[-1]
        assert binds["chave"] == "modelo_ia"
        assert binds["valor"] == "openai.gpt-oss-120b"


class TestProvedorIa:
    def test_sem_configuracao_devolve_ollama(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(linha_fetchone=None))

        assert mod.provedor_ia() == "ollama"

    def test_devolve_o_valor_gravado(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(linha_fetchone=("oci_openai",)))

        assert mod.provedor_ia() == "oci_openai"

    def test_definir_grava_como_texto(self, monkeypatch):
        cursor = _CursorFake(rowcount=0)
        _conexao_fake_para(monkeypatch, cursor)

        mod.definir_provedor_ia("oci_openai")

        _sql, binds = cursor.execucoes[-1]
        assert binds["chave"] == "provedor_ia"
        assert binds["valor"] == "oci_openai"


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
