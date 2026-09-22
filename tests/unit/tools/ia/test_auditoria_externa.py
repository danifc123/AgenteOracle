import contextlib

import psycopg

from agente_oracle.tools.ia import auditoria_externa as mod


class _CursorFake:
    def __init__(self, levantar: Exception | None = None, linha_fetchone=(0,)):
        self._levantar = levantar
        self._linha_fetchone = linha_fetchone
        self.execucoes: list[tuple[str, dict]] = []

    def execute(self, sql: str, **binds):
        if self._levantar:
            raise self._levantar
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


class TestRegistrar:
    def test_grava_dominio_host_tamanho_e_hash(self, monkeypatch):
        cursor = _CursorFake()
        _conexao_fake_para(monkeypatch, cursor)

        mod.registrar("ti", "http://127.0.0.1:11434", "Sistema não libera acesso")

        # execucoes[0] é o CREATE TABLE (_garantir_tabela); o INSERT é o último.
        _sql, binds = cursor.execucoes[-1]
        assert binds["dominio"] == "ti"
        assert binds["host"] == "http://127.0.0.1:11434"
        assert binds["tamanho"] == len("Sistema não libera acesso")
        assert binds["hash_conteudo"] != "Sistema não libera acesso"
        assert len(binds["hash_conteudo"]) == 64  # sha256 em hex

    def test_falha_no_postgres_nunca_levanta(self, monkeypatch):
        cursor = _CursorFake(levantar=psycopg.Error("fora do ar"))
        _conexao_fake_para(monkeypatch, cursor)

        mod.registrar("ti", "http://127.0.0.1:11434", "qualquer texto")  # não deveria levantar


class TestContagemHoje:
    def test_devolve_a_contagem_do_banco(self, monkeypatch):
        cursor = _CursorFake(linha_fetchone=(7,))
        _conexao_fake_para(monkeypatch, cursor)

        assert mod.contagem_hoje("ti") == 7

    def test_falha_no_postgres_devolve_zero(self, monkeypatch):
        cursor = _CursorFake(levantar=psycopg.Error("fora do ar"))
        _conexao_fake_para(monkeypatch, cursor)

        assert mod.contagem_hoje("ti") == 0
