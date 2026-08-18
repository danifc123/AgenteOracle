from datetime import date

from agente_oracle.agent.financeiro.classificacao_contabil import (
    LancamentoContabil,
    _chave_historico,
    construir_dicionario,
    mapa_conta_descricao,
    sugerir_classificacoes,
)


def _lancamento(
    documento: str = "1",
    linha: str = "1",
    conta: str = "-1",
    conta_descricao: str | None = None,
    historico: str = "BX.PAG. 0  /000000254/  -BRASILSEG COMPA",
    valor: float = 100.0,
    data_movimentacao: date = date(2026, 1, 15),
) -> LancamentoContabil:
    return LancamentoContabil(
        documento=documento,
        linha=linha,
        conta=conta,
        conta_descricao=conta_descricao,
        historico=historico,
        valor=valor,
        data_movimentacao=data_movimentacao,
    )


class TestChaveHistorico:
    def test_ignora_numero_de_documento(self):
        chave_a = _chave_historico("BX.PAG. 0  /000000254/  -BRASILSEG COMPA")
        chave_b = _chave_historico("BX.PAG. 0  /000000256/  -BRASILSEG COMPA")
        assert chave_a == chave_b

    def test_ignora_acento_e_caixa(self):
        assert _chave_historico("Pagamento de Água") == _chave_historico("PAGAMENTO DE AGUA")

    def test_historico_diferente_gera_chave_diferente(self):
        assert _chave_historico("BX.PAG. -BRASILSEG") != _chave_historico("BX.PAG. -OUTRA SEGURADORA")


class TestConstruirDicionario:
    def test_ignora_lancamentos_sem_conta(self):
        classificados = [_lancamento(conta="-1"), _lancamento(conta="-1")]
        assert construir_dicionario(classificados) == {}

    def test_conta_conta_por_chave(self):
        classificados = [
            _lancamento(conta="2102010001", historico="BX.PAG. 0 /000000254/ -BRASILSEG"),
            _lancamento(conta="2102010001", historico="BX.PAG. 0 /000000256/ -BRASILSEG"),
            _lancamento(conta="1101020001", historico="BX.PAG. 0 /000000260/ -OUTRA"),
        ]
        dicionario = construir_dicionario(classificados)
        chave_brasilseg = _chave_historico("BX.PAG. 0 /000000254/ -BRASILSEG")
        assert dicionario[chave_brasilseg]["2102010001"] == 2


class TestMapaContaDescricao:
    def test_mapeia_conta_para_descricao_ignorando_nao_definida(self):
        classificados = [
            _lancamento(conta="2102010001", conta_descricao="FORNECEDORES NACIONAIS"),
            _lancamento(conta="-1", conta_descricao=None),
        ]
        mapa = mapa_conta_descricao(classificados)
        assert mapa == {"2102010001": "FORNECEDORES NACIONAIS"}


class TestSugerirClassificacoes:
    def _dicionario_confiante(self):
        classificados = [
            _lancamento(
                conta="2102010001", conta_descricao="FORNECEDORES NACIONAIS", historico="BX.PAG. 0 /1/ -X"
            ),
            _lancamento(
                conta="2102010001", conta_descricao="FORNECEDORES NACIONAIS", historico="BX.PAG. 0 /2/ -X"
            ),
            _lancamento(
                conta="2102010001", conta_descricao="FORNECEDORES NACIONAIS", historico="BX.PAG. 0 /3/ -X"
            ),
        ]
        return construir_dicionario(classificados), mapa_conta_descricao(classificados)

    def test_sugere_quando_confianca_e_suporte_batem(self):
        dicionario, descricoes = self._dicionario_confiante()
        nao_classificados = [_lancamento(conta="-1", historico="BX.PAG. 0 /9/ -X", valor=500.0)]

        sugestoes = sugerir_classificacoes(nao_classificados, dicionario, descricoes)

        assert len(sugestoes) == 1
        sugestao = sugestoes[0]
        assert sugestao.conta_sugerida == "2102010001"
        assert sugestao.conta_descricao_sugerida == "FORNECEDORES NACIONAIS"
        assert sugestao.confianca_percentual == 100.0
        assert sugestao.suporte_historico == 3

    def test_nao_sugere_sem_suporte_minimo(self):
        classificados = [_lancamento(conta="2102010001", historico="BX.PAG. 0 /1/ -X")]
        dicionario = construir_dicionario(classificados)
        descricoes = mapa_conta_descricao(classificados)
        nao_classificados = [_lancamento(conta="-1", historico="BX.PAG. 0 /9/ -X")]

        assert sugerir_classificacoes(nao_classificados, dicionario, descricoes) == []

    def test_nao_sugere_abaixo_do_limiar_de_confianca(self):
        classificados = [
            _lancamento(conta="A", historico="BX.PAG. 0 /1/ -X"),
            _lancamento(conta="A", historico="BX.PAG. 0 /2/ -X"),
            _lancamento(conta="B", historico="BX.PAG. 0 /3/ -X"),
        ]
        dicionario = construir_dicionario(classificados)
        descricoes = mapa_conta_descricao(classificados)
        nao_classificados = [_lancamento(conta="-1", historico="BX.PAG. 0 /9/ -X")]

        assert sugerir_classificacoes(nao_classificados, dicionario, descricoes) == []

    def test_sem_precedente_nenhum_nao_sugere(self):
        dicionario, descricoes = self._dicionario_confiante()
        nao_classificados = [_lancamento(conta="-1", historico="HISTORICO NUNCA VISTO ANTES")]

        assert sugerir_classificacoes(nao_classificados, dicionario, descricoes) == []

    def test_ordena_por_maior_valor_absoluto_primeiro(self):
        dicionario, descricoes = self._dicionario_confiante()
        nao_classificados = [
            _lancamento(documento="pequeno", conta="-1", historico="BX.PAG. 0 /9/ -X", valor=10.0),
            _lancamento(documento="grande", conta="-1", historico="BX.PAG. 0 /9/ -X", valor=-500.0),
        ]

        sugestoes = sugerir_classificacoes(nao_classificados, dicionario, descricoes)

        assert [sugestao.documento for sugestao in sugestoes] == ["grande", "pequeno"]
