import pytest

from agente_oracle.tools.financeiro.consulta_livre import (
    LIMITE_MAXIMO_LINHAS,
    PALAVRAS_BLOQUEADAS,
    ConsultaFinanceiraInvalida,
    _validar_consulta,
)

_VIEW_PERMITIDA = "vw_titulos_pagar"


def test_select_simples_valido_ganha_limite_automatico():
    resultado = _validar_consulta(f"SELECT * FROM {_VIEW_PERMITIDA}")
    assert resultado.endswith(f"FETCH FIRST {LIMITE_MAXIMO_LINHAS} ROWS ONLY")


def test_sql_vazio_e_rejeitado():
    with pytest.raises(ConsultaFinanceiraInvalida, match="vazia"):
        _validar_consulta("   ")


def test_ponto_e_virgula_no_meio_e_rejeitado():
    with pytest.raises(ConsultaFinanceiraInvalida, match="única instrução"):
        _validar_consulta(f"SELECT * FROM {_VIEW_PERMITIDA}; SELECT 1")


def test_sql_que_nao_comeca_com_select_ou_with_e_rejeitado():
    with pytest.raises(ConsultaFinanceiraInvalida, match="SELECT"):
        _validar_consulta(f"EXPLAIN SELECT * FROM {_VIEW_PERMITIDA}")


@pytest.mark.parametrize("palavra", PALAVRAS_BLOQUEADAS)
def test_bloqueia_todas_as_palavras_proibidas(palavra):
    sql = f"SELECT * FROM {_VIEW_PERMITIDA} WHERE 1=1 {palavra} algo"
    with pytest.raises(ConsultaFinanceiraInvalida):
        _validar_consulta(sql)


def test_juncao_por_virgula_e_rejeitada():
    """Exploit corrigido nesta sessão: `FROM a, b` deixava a whitelist de
    tabelas enxergar só `a`, permitindo ler qualquer tabela via `b`."""
    sql = f"SELECT u.usuario, u.senha_hash FROM {_VIEW_PERMITIDA} t, usuarios u"
    with pytest.raises(ConsultaFinanceiraInvalida, match="JOIN"):
        _validar_consulta(sql)


def test_tabela_fora_da_whitelist_e_rejeitada():
    with pytest.raises(ConsultaFinanceiraInvalida, match="fora do escopo"):
        _validar_consulta("SELECT * FROM usuarios")


def test_cte_e_aceita_sem_ser_cobrada_como_tabela():
    sql = f"WITH ranking AS (SELECT * FROM {_VIEW_PERMITIDA}) SELECT * FROM ranking"
    resultado = _validar_consulta(sql)
    assert "FETCH FIRST" in resultado


@pytest.mark.parametrize(
    "sufixo",
    ["LIMIT 10", "FETCH FIRST 5 ROWS ONLY", "WHERE ROWNUM <= 5"],
)
def test_nao_duplica_limite_quando_ja_existe_um(sufixo):
    sql = f"SELECT * FROM {_VIEW_PERMITIDA} {sufixo}"
    resultado = _validar_consulta(sql)
    assert resultado.upper().count("FETCH FIRST") <= 1
