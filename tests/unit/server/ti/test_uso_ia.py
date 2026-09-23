from agente_oracle.server.ti import uso_ia as uso_ia_module
from agente_oracle.server.ti.uso_ia import (
    _acesso_negado,
    _chamados_ia_para_json,
    _corpo_uso_ia,
    _dias_da_query,
    _linha_dia_para_json,
    _linha_para_json,
    _linha_usuario_para_json,
    _nome_usuario,
)
from agente_oracle.tools.ia.auditoria_externa import (
    ResumoTokensDia,
    ResumoTokensProvedor,
    ResumoTokensUsuario,
)
from agente_oracle.tools.ti.uso_ia_chamados import ResumoUsoIa


class TestDiasDaQuery:
    def test_ausente_usa_padrao(self):
        assert _dias_da_query(None) == 30

    def test_numero_valido_e_usado(self):
        assert _dias_da_query("7") == 7

    def test_nao_numerico_usa_padrao(self):
        assert _dias_da_query("abc") == 30


class TestLinhaParaJson:
    def test_soma_tokens_entrada_e_saida_e_inclui_raciocinio(self):
        linha = ResumoTokensProvedor(
            provedor="oci_openai",
            modelo="openai.gpt-oss-120b",
            chamadas=2,
            tokens_entrada_total=134,
            tokens_saida_total=96,
            tokens_raciocinio_total=62,
        )

        corpo = _linha_para_json(linha)

        assert corpo == {
            "provedor": "oci_openai",
            "modelo": "openai.gpt-oss-120b",
            "chamadas": 2,
            "tokens_entrada": 134,
            "tokens_saida": 96,
            "tokens_raciocinio": 62,
            "tokens_total": 230,
        }


class TestNomeUsuario:
    def test_usuario_sistema_vira_rotulo_fixo(self):
        assert _nome_usuario("sistema", {}) == "Sistema/Automático"

    def test_usuario_existente_usa_o_nome_do_mapa(self):
        assert _nome_usuario("42", {"42": "Daniel Faria"}) == "Daniel Faria"

    def test_usuario_removido_cai_no_fallback_com_o_id(self):
        assert _nome_usuario("99", {}) == "Usuário #99 (removido)"


class TestLinhaUsuarioParaJson:
    def test_monta_o_corpo_com_nome_resolvido(self):
        linha = ResumoTokensUsuario(
            usuario_id="42",
            chamadas=5,
            tokens_entrada_total=300,
            tokens_saida_total=150,
            tokens_raciocinio_total=0,
        )

        corpo = _linha_usuario_para_json(linha, {"42": "Daniel Faria"})

        assert corpo == {
            "usuario_id": "42",
            "nome": "Daniel Faria",
            "chamadas": 5,
            "tokens_entrada": 300,
            "tokens_saida": 150,
            "tokens_raciocinio": 0,
            "tokens_total": 450,
        }


class TestLinhaDiaParaJson:
    def test_soma_tokens_entrada_e_saida(self):
        linha = ResumoTokensDia(data="2026-09-23", chamadas=5, tokens_entrada_total=300, tokens_saida_total=150)

        assert _linha_dia_para_json(linha) == {
            "data": "2026-09-23",
            "chamadas": 5,
            "tokens_entrada": 300,
            "tokens_saida": 150,
            "tokens_total": 450,
        }


class TestChamadosIaParaJson:
    def test_monta_o_corpo_a_partir_do_resumo_uso(self):
        resumo = ResumoUsoIa(
            total_chamados=40,
            total_avaliados_insuficientes=6,
            total_com_fallback_embedding=2,
            duracao_total_ms=120000,
            duracao_media_ms=3000.0,
        )

        assert _chamados_ia_para_json(resumo) == {
            "total_chamados": 40,
            "avaliados_insuficientes": 6,
            "com_fallback_embedding": 2,
            "duracao_media_ms": 3000.0,
        }


class TestCorpoUsoIa:
    def test_junta_provedor_usuario_dia_e_chamados_ia(self, monkeypatch):
        monkeypatch.setattr(
            uso_ia_module.auditoria_externa,
            "resumo_por_provedor",
            lambda dias: [ResumoTokensProvedor("ollama", "qwen2.5-coder:7b", 3, 300, 150, 0)],
        )
        monkeypatch.setattr(
            uso_ia_module.auditoria_externa,
            "resumo_por_usuario",
            lambda dias: [ResumoTokensUsuario("42", 3, 300, 150, 0)],
        )
        monkeypatch.setattr(
            uso_ia_module.auditoria_externa,
            "resumo_diario",
            lambda dias: [ResumoTokensDia("2026-09-23", 3, 300, 150)],
        )
        monkeypatch.setattr(uso_ia_module.auditoria_externa, "tokens_hoje", lambda dominio: 450)
        monkeypatch.setattr(uso_ia_module.usuarios, "listar_usuarios", lambda: [{"id": 42, "nome": "Daniel Faria"}])
        monkeypatch.setattr(
            uso_ia_module.uso_ia_chamados,
            "resumo_uso",
            lambda dias: ResumoUsoIa(10, 2, 1, 5000, 500.0),
        )

        corpo = _corpo_uso_ia(dias=30)

        assert corpo["consumo"][0]["provedor"] == "ollama"
        assert corpo["por_usuario"][0]["nome"] == "Daniel Faria"
        assert corpo["por_dia"] == [
            {"data": "2026-09-23", "chamadas": 3, "tokens_entrada": 300, "tokens_saida": 150, "tokens_total": 450}
        ]
        assert corpo["tokens_hoje_por_dominio"] == {"ti": 450, "rh": 450}
        assert corpo["chamados_ia"] == {
            "total_chamados": 10,
            "avaliados_insuficientes": 2,
            "com_fallback_embedding": 1,
            "duracao_media_ms": 500.0,
        }


class TestAcessoNegado:
    def test_desenvolvedor_pode_acessar(self):
        assert _acesso_negado({"papeis": ["desenvolvedor"]}) is None

    def test_usuario_de_ti_comum_e_barrado(self):
        assert _acesso_negado({"papeis": ["ti_admin"]}) == "Acesso restrito a desenvolvedores."

    def test_sem_papeis_e_barrado(self):
        assert _acesso_negado({}) == "Acesso restrito a desenvolvedores."
