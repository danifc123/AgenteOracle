import contextlib
from datetime import UTC, datetime
from decimal import Decimal

import psycopg
import pytest

from agente_oracle.tools.ia import provedores_llm as mod
from agente_oracle.tools.ia.provedores_llm import ProvedorLLM, ProvedorLlmJaExiste


def _erro_postgres(sqlstate: str) -> psycopg.Error:
    erro = psycopg.Error("erro simulado")
    erro.sqlstate = sqlstate
    return erro


class _CursorFake:
    def __init__(
        self,
        linha_fetchone: tuple | None = None,
        linhas_fetchall: list[tuple] | None = None,
        rowcount: int = 1,
        erro_ao_executar: Exception | None = None,
    ):
        self._linha_fetchone = linha_fetchone
        self._linhas_fetchall = linhas_fetchall or []
        self.rowcount = rowcount
        self._erro_ao_executar = erro_ao_executar
        self.execucoes: list[tuple[str, dict]] = []

    def execute(self, sql: str, **binds):
        self.execucoes.append((sql, binds))
        if self._erro_ao_executar is not None:
            raise self._erro_ao_executar
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


_LINHA_CRUA = (
    1,
    "OCI Generative AI — gpt-oss-120b",
    "openai_compativel",
    "https://inference.generativeai.sa-saopaulo-1.oci.oraclecloud.com/openai/v1",
    "sk-segredo",
    "ocid1.generativeaiproject.oc1...",
    "openai.gpt-oss-120b",
    "responses",
    Decimal("0.01"),
    Decimal("0.02"),
    "R$",
    datetime(2026, 9, 23, tzinfo=UTC),
)


class TestListar:
    def test_mapeia_cada_linha_pra_provedorllm(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(linhas_fetchall=[_LINHA_CRUA]))

        provedores = mod.listar()

        assert len(provedores) == 1
        assert provedores[0] == ProvedorLLM(
            id=1,
            nome="OCI Generative AI — gpt-oss-120b",
            tipo_conexao="openai_compativel",
            base_url="https://inference.generativeai.sa-saopaulo-1.oci.oraclecloud.com/openai/v1",
            api_key="sk-segredo",
            projeto_id="ocid1.generativeaiproject.oc1...",
            modelo="openai.gpt-oss-120b",
            estilo_api="responses",
            preco_entrada_por_1k=Decimal("0.01"),
            preco_saida_por_1k=Decimal("0.02"),
            moeda="R$",
            criado_em=datetime(2026, 9, 23, tzinfo=UTC),
        )

    def test_lista_vazia_nao_quebra(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(linhas_fetchall=[]))

        assert mod.listar() == []

    def test_api_key_e_projeto_id_nulos_viram_string_vazia(self, monkeypatch):
        linha = list(_LINHA_CRUA)
        linha[4] = None  # api_key
        linha[5] = None  # projeto_id
        _conexao_fake_para(monkeypatch, _CursorFake(linhas_fetchall=[tuple(linha)]))

        provedor = mod.listar()[0]

        assert provedor.api_key == ""
        assert provedor.projeto_id == ""


class TestBuscar:
    def test_encontrado_devolve_provedorllm(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(linha_fetchone=_LINHA_CRUA))

        assert mod.buscar(1).id == 1

    def test_nao_encontrado_devolve_none(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(linha_fetchone=None))

        assert mod.buscar(999) is None


class TestCriar:
    def _campos(self, **overrides) -> dict:
        campos = {
            "nome": "Ollama local — teste",
            "tipo_conexao": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "api_key": "",
            "projeto_id": "",
            "modelo": "qwen2.5-coder:7b",
            "estilo_api": "chat_completions",
            "preco_entrada_por_1k": Decimal("0"),
            "preco_saida_por_1k": Decimal("0"),
            "moeda": "R$",
        }
        campos.update(overrides)
        return campos

    def test_insere_e_devolve_o_provedor_criado(self, monkeypatch):
        cursor = _CursorFake(linha_fetchone=_LINHA_CRUA)
        _conexao_fake_para(monkeypatch, cursor)

        provedor = mod.criar(**self._campos())

        assert provedor.id == 1
        _sql, binds = cursor.execucoes[-1]
        assert binds["nome"] == "Ollama local — teste"

    def test_api_key_vazia_grava_none_nao_string_vazia(self, monkeypatch):
        cursor = _CursorFake(linha_fetchone=_LINHA_CRUA)
        _conexao_fake_para(monkeypatch, cursor)

        mod.criar(**self._campos(api_key=""))

        _sql, binds = cursor.execucoes[-1]
        assert binds["api_key"] is None

    def test_nome_duplicado_levanta_provedorllmjaexiste(self, monkeypatch):
        cursor = _CursorFake(erro_ao_executar=_erro_postgres("23505"))
        _conexao_fake_para(monkeypatch, cursor)

        with pytest.raises(ProvedorLlmJaExiste):
            mod.criar(**self._campos(nome="Já existe"))

    def test_outro_erro_de_banco_nao_vira_provedorllmjaexiste(self, monkeypatch):
        cursor = _CursorFake(erro_ao_executar=_erro_postgres("42703"))
        _conexao_fake_para(monkeypatch, cursor)

        with pytest.raises(psycopg.Error):
            mod.criar(**self._campos())


class TestAtualizar:
    def test_sem_campos_so_busca_sem_executar_update(self, monkeypatch):
        chamadas = []
        monkeypatch.setattr(mod, "buscar", lambda id_provedor: chamadas.append(id_provedor) or "resultado-busca")

        resultado = mod.atualizar(1)

        assert resultado == "resultado-busca"
        assert chamadas == [1]

    def test_com_campos_monta_update_so_com_o_que_foi_passado(self, monkeypatch):
        cursor = _CursorFake(linha_fetchone=_LINHA_CRUA)
        _conexao_fake_para(monkeypatch, cursor)

        mod.atualizar(1, nome="Novo nome", preco_entrada_por_1k=Decimal("0.05"))

        sql, binds = cursor.execucoes[-1]
        assert "nome = :nome" in sql
        assert "preco_entrada_por_1k = :preco_entrada_por_1k" in sql
        assert "base_url = :base_url" not in sql
        assert binds["nome"] == "Novo nome"
        assert binds["preco_entrada_por_1k"] == Decimal("0.05")
        assert "base_url" not in binds

    def test_id_inexistente_devolve_none(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(linha_fetchone=None))

        assert mod.atualizar(999, nome="qualquer") is None

    def test_nome_duplicado_levanta_provedorllmjaexiste(self, monkeypatch):
        cursor = _CursorFake(erro_ao_executar=_erro_postgres("23505"))
        _conexao_fake_para(monkeypatch, cursor)

        with pytest.raises(ProvedorLlmJaExiste):
            mod.atualizar(1, nome="Já existe")


class TestRemover:
    def test_rowcount_maior_que_zero_devolve_true(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(rowcount=1))

        assert mod.remover(1) is True

    def test_rowcount_zero_devolve_false(self, monkeypatch):
        _conexao_fake_para(monkeypatch, _CursorFake(rowcount=0))

        assert mod.remover(999) is False


class TestCustoEstimado:
    def test_multiplica_tokens_por_preco_por_mil(self):
        provedor = ProvedorLLM(
            id=1,
            nome="teste",
            tipo_conexao="ollama",
            base_url="http://x",
            api_key="",
            projeto_id="",
            modelo="m",
            estilo_api="chat_completions",
            preco_entrada_por_1k=Decimal("0.01"),
            preco_saida_por_1k=Decimal("0.02"),
            moeda="R$",
            criado_em=datetime.now(UTC),
        )

        custo = mod.custo_estimado(2000, 1000, provedor)

        assert custo == Decimal("0.04")  # (2000/1000 * 0.01) + (1000/1000 * 0.02)

    def test_zero_tokens_devolve_zero(self):
        provedor = ProvedorLLM(
            id=1,
            nome="teste",
            tipo_conexao="ollama",
            base_url="http://x",
            api_key="",
            projeto_id="",
            modelo="m",
            estilo_api="chat_completions",
            preco_entrada_por_1k=Decimal("1"),
            preco_saida_por_1k=Decimal("1"),
            moeda="R$",
            criado_em=datetime.now(UTC),
        )

        assert mod.custo_estimado(0, 0, provedor) == Decimal("0")


class TestTipoConexaoValido:
    @pytest.mark.parametrize("valor", ["ollama", "openai_compativel"])
    def test_valores_validos_sao_aceitos(self, valor):
        assert mod.tipo_conexao_valido(valor) is True

    @pytest.mark.parametrize("valor", ["", "oci", "OLLAMA", "openai"])
    def test_valores_invalidos_sao_rejeitados(self, valor):
        assert mod.tipo_conexao_valido(valor) is False


class TestEstiloApiValido:
    @pytest.mark.parametrize("valor", ["chat_completions", "responses"])
    def test_valores_validos_sao_aceitos(self, valor):
        assert mod.estilo_api_valido(valor) is True

    @pytest.mark.parametrize("valor", ["", "response", "CHAT_COMPLETIONS"])
    def test_valores_invalidos_sao_rejeitados(self, valor):
        assert mod.estilo_api_valido(valor) is False
