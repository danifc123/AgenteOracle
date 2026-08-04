import io

import pytest
from openpyxl import Workbook, load_workbook

from agente_oracle.tools.ferramentas.juntar_excel import ArquivoExcelInvalido, juntar_planilhas


def _bytes_planilha(cabecalho: list[str], linhas: list[list]) -> bytes:
    workbook = Workbook()
    planilha = workbook.active
    planilha.append(cabecalho)
    for linha in linhas:
        planilha.append(linha)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class TestJuntarPlanilhas:
    def test_colunas_iguais_empilha_num_bloco_so(self) -> None:
        arquivo1 = _bytes_planilha(["nome", "idade"], [["Ana", 30]])
        arquivo2 = _bytes_planilha(["nome", "idade"], [["Bruno", 25]])

        resultado = load_workbook(io.BytesIO(juntar_planilhas(arquivo1, arquivo2)))
        planilha = resultado.active
        linhas = list(planilha.iter_rows(values_only=True))

        assert linhas == [("nome", "idade"), ("Ana", 30), ("Bruno", 25)]

    def test_colunas_iguais_em_ordem_diferente_reordena_segunda_planilha(self) -> None:
        arquivo1 = _bytes_planilha(["nome", "idade"], [["Ana", 30]])
        arquivo2 = _bytes_planilha(["idade", "nome"], [[25, "Bruno"]])

        resultado = load_workbook(io.BytesIO(juntar_planilhas(arquivo1, arquivo2)))
        linhas = list(resultado.active.iter_rows(values_only=True))

        assert linhas == [("nome", "idade"), ("Ana", 30), ("Bruno", 25)]

    def test_colunas_iguais_nao_aplica_cor_de_fundo(self) -> None:
        arquivo1 = _bytes_planilha(["nome"], [["Ana"]])
        arquivo2 = _bytes_planilha(["nome"], [["Bruno"]])

        resultado = load_workbook(io.BytesIO(juntar_planilhas(arquivo1, arquivo2)))
        planilha = resultado.active

        for linha in planilha.iter_rows():
            for celula in linha:
                assert celula.fill.fgColor.rgb in (None, "00000000")

    def test_colunas_diferentes_mantem_dois_blocos_com_cores(self) -> None:
        arquivo1 = _bytes_planilha(["nome"], [["Ana"]])
        arquivo2 = _bytes_planilha(["produto"], [["Caneta"]])

        resultado = load_workbook(io.BytesIO(juntar_planilhas(arquivo1, arquivo2)))
        planilha = resultado.active
        linhas = list(planilha.iter_rows(values_only=True))

        assert linhas == [("nome",), ("Ana",), (None,), ("produto",), ("Caneta",)]

        cabecalho1 = planilha["A1"]
        dado1 = planilha["A2"]
        cabecalho2 = planilha["A4"]
        dado2 = planilha["A5"]

        assert cabecalho1.fill.fgColor.rgb == "00D9F2D9"
        assert dado1.fill.fgColor.rgb == "00D9F2D9"
        assert cabecalho2.fill.fgColor.rgb == "00FCE4D6"
        assert dado2.fill.fgColor.rgb == "00FCE4D6"

    def test_arquivo_invalido_levanta_erro(self) -> None:
        arquivo_valido = _bytes_planilha(["nome"], [["Ana"]])

        with pytest.raises(ArquivoExcelInvalido):
            juntar_planilhas(b"isso nao e um xlsx", arquivo_valido)
