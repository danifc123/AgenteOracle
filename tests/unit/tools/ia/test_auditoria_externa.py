import contextlib

import psycopg

from agente_oracle.tools.ia import auditoria_externa as mod


class _CursorFake:
    def __init__(self, linha_fetchone=None, linhas_fetchall=None, levantar: Exception | None = None):
        self._linha_fetchone = linha_fetchone
        self._linhas_fetchall = linhas_fetchall or []
        self._levantar = levantar
        self.execucoes: list[tuple[str, dict]] = []

    def execute(self, sql: str, **binds):
        if self._levantar:
            raise self._levantar
        self.execucoes.append((sql, binds))
        return self

    def fetchone(self):
        return self._linha_fetchone

    def fetchall(self):
        return self._linhas_fetchall


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


def _registrar(**overrides) -> None:
    parametros = {
        "dominio": "ti",
        "host": "http://127.0.0.1:11434",
        "texto": "texto qualquer",
        "provedor": "ollama",
        "modelo": "qwen2.5-coder:7b",
        "tokens_entrada": 10,
        "tokens_saida": 5,
        "tokens_raciocinio": None,
        "usuario_id": "usuario-teste",
    }
    parametros.update(overrides)
    mod.registrar(**parametros)


class TestRegistrar:
    def test_grava_provedor_modelo_e_tokens(self, monkeypatch):
        cursor = _CursorFake()
        _conexao_fake_para(monkeypatch, cursor)

        _registrar(
            provedor="oci_openai",
            modelo="openai.gpt-oss-120b",
            tokens_entrada=67,
            tokens_saida=48,
            tokens_raciocinio=31,
        )

        _sql, binds = cursor.execucoes[-1]
        assert binds["provedor"] == "oci_openai"
        assert binds["modelo"] == "openai.gpt-oss-120b"
        assert binds["tokens_entrada"] == 67
        assert binds["tokens_saida"] == 48
        assert binds["tokens_raciocinio"] == 31

    def test_aceita_tokens_none(self, monkeypatch):
        cursor = _CursorFake()
        _conexao_fake_para(monkeypatch, cursor)

        _registrar(tokens_entrada=None, tokens_saida=None)

        _sql, binds = cursor.execucoes[-1]
        assert binds["tokens_entrada"] is None
        assert binds["tokens_saida"] is None
        assert binds["tokens_raciocinio"] is None

    def test_falha_de_banco_nao_levanta(self, monkeypatch):
        cursor = _CursorFake(levantar=psycopg.Error("fora do ar"))
        _conexao_fake_para(monkeypatch, cursor)

        _registrar()  # não deve levantar

    def test_grava_usuario_id(self, monkeypatch):
        cursor = _CursorFake()
        _conexao_fake_para(monkeypatch, cursor)

        _registrar(usuario_id="sistema")

        _sql, binds = cursor.execucoes[-1]
        assert binds["usuario_id"] == "sistema"


class TestResumoPorProvedor:
    def test_agrega_por_provedor_e_modelo(self, monkeypatch):
        cursor = _CursorFake(
            linhas_fetchall=[
                ("ollama", "qwen2.5-coder:7b", 3, 300, 150, 0),
                ("oci_openai", "openai.gpt-oss-120b", 2, 134, 96, 62),
            ]
        )
        _conexao_fake_para(monkeypatch, cursor)

        resumo = mod.resumo_por_provedor(dias=30)

        assert resumo == [
            mod.ResumoTokensProvedor("ollama", "qwen2.5-coder:7b", 3, 300, 150, 0),
            mod.ResumoTokensProvedor("oci_openai", "openai.gpt-oss-120b", 2, 134, 96, 62),
        ]

    def test_sem_chamadas_devolve_lista_vazia(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(linhas_fetchall=[]))

        assert mod.resumo_por_provedor(dias=30) == []


class TestResumoPorUsuario:
    def test_agrega_por_usuario_ordenado_por_consumo_total_desc(self, monkeypatch):
        cursor = _CursorFake(
            linhas_fetchall=[
                ("42", 5, 400, 200, 0),
                ("sistema", 20, 150, 80, 0),
            ]
        )
        _conexao_fake_para(monkeypatch, cursor)

        resumo = mod.resumo_por_usuario(dias=30)

        assert resumo == [
            mod.ResumoTokensUsuario("42", 5, 400, 200, 0),
            mod.ResumoTokensUsuario("sistema", 20, 150, 80, 0),
        ]

    def test_sql_ordena_por_soma_de_tokens_descendente(self, monkeypatch):
        # Não dá pra testar a ordenação real sem Postgres de verdade (o
        # fake só devolve o que a gente passou) — confere que o SQL emitido
        # pede ORDER BY DESC, é o contrato que importa aqui.
        cursor = _CursorFake(linhas_fetchall=[])
        _conexao_fake_para(monkeypatch, cursor)

        mod.resumo_por_usuario(dias=30)

        sql, _binds = cursor.execucoes[-1]
        assert "ORDER BY" in sql
        assert "DESC" in sql

    def test_sem_chamadas_devolve_lista_vazia(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(linhas_fetchall=[]))

        assert mod.resumo_por_usuario(dias=30) == []


class TestResumoDiario:
    def test_agrega_por_dia_do_mais_antigo_pro_mais_recente(self, monkeypatch):
        cursor = _CursorFake(
            linhas_fetchall=[
                ("2026-09-22", 3, 300, 150),
                ("2026-09-23", 5, 500, 250),
            ]
        )
        _conexao_fake_para(monkeypatch, cursor)

        resumo = mod.resumo_diario(dias=14)

        assert resumo == [
            mod.ResumoTokensDia("2026-09-22", 3, 300, 150),
            mod.ResumoTokensDia("2026-09-23", 5, 500, 250),
        ]

    def test_sql_ordena_do_mais_antigo_pro_mais_recente(self, monkeypatch):
        cursor = _CursorFake(linhas_fetchall=[])
        _conexao_fake_para(monkeypatch, cursor)

        mod.resumo_diario(dias=14)

        sql, _binds = cursor.execucoes[-1]
        assert "ORDER BY" in sql
        assert "ASC" in sql

    def test_sem_chamadas_devolve_lista_vazia(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(linhas_fetchall=[]))

        assert mod.resumo_diario(dias=14) == []


class TestTokensHoje:
    def test_soma_entrada_e_saida(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(linha_fetchone=(150,)))

        assert mod.tokens_hoje("ti") == 150

    def test_falha_de_banco_devolve_zero(self, monkeypatch):
        cursor = _CursorFake(levantar=psycopg.Error("fora do ar"))
        _conexao_fake_para(monkeypatch, cursor)

        assert mod.tokens_hoje("ti") == 0
