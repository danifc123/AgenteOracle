from agente_oracle.tools.financeiro.historico import hash_sql


def test_espacamento_diferente_gera_mesmo_hash():
    sql_a = "SELECT a, b FROM vw_titulos_pagar WHERE valor > 100"
    sql_b = "SELECT   a,  b   FROM  vw_titulos_pagar   WHERE valor > 100"
    assert hash_sql(sql_a) == hash_sql(sql_b)


def test_maiusculas_minusculas_diferentes_geram_mesmo_hash():
    sql_a = "select a, b from vw_titulos_pagar where valor > 100"
    sql_b = "SELECT A, B FROM VW_TITULOS_PAGAR WHERE VALOR > 100"
    assert hash_sql(sql_a) == hash_sql(sql_b)


def test_colunas_em_ordem_diferente_geram_mesmo_hash():
    sql_a = "SELECT a, b, c FROM vw_titulos_pagar"
    sql_b = "SELECT c, a, b FROM vw_titulos_pagar"
    assert hash_sql(sql_a) == hash_sql(sql_b)


def test_where_diferente_gera_hash_diferente():
    sql_a = "SELECT a FROM vw_titulos_pagar WHERE valor > 100"
    sql_b = "SELECT a FROM vw_titulos_pagar WHERE valor > 200"
    assert hash_sql(sql_a) != hash_sql(sql_b)


def test_consulta_com_cte_nao_quebra_mesmo_sem_casar_o_regex():
    sql = "WITH x AS (SELECT a FROM vw_titulos_pagar) SELECT * FROM x"
    resultado = hash_sql(sql)
    assert isinstance(resultado, str)
    assert len(resultado) == 64  # sha256 em hexdigest
