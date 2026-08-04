"""Lógica pura (sem HTTP) de junção de duas planilhas `.xlsx` — ver
`server/ferramentas/juntar_excel.py` para a rota que expõe isso via upload.
Regra de negócio: colunas iguais (mesmo conjunto de nomes, ordem não importa)
empilha tudo num bloco só; colunas diferentes mantém os dois blocos
separados, com fundo verde clarinho pro 1º arquivo e laranja clarinho pro 2º
— mesmas cores usadas no preview do frontend (`D9F2D9`/`FCE4D6`)."""

import io

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

_VERDE_CLARO = PatternFill(start_color="D9F2D9", end_color="D9F2D9", fill_type="solid")
_LARANJA_CLARO = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
_LARGURA_MAXIMA_COLUNA = 50


class ArquivoExcelInvalido(Exception):
    """Levantada quando um dos arquivos enviados não é um .xlsx válido."""


def _ler_planilha(conteudo: bytes) -> tuple[list[str], list[list]]:
    """Lê a planilha ATIVA de um .xlsx: 1ª linha vira cabeçalho, o resto vira
    linhas de dado. `data_only=True` lê o valor calculado de fórmula (não a
    fórmula em si) — mais previsível pra planilha de origem desconhecida."""
    try:
        workbook = load_workbook(io.BytesIO(conteudo), data_only=True)
    except Exception as erro:
        raise ArquivoExcelInvalido(f"Não foi possível ler o arquivo: {erro}") from erro

    linhas = list(workbook.active.iter_rows(values_only=True))
    if not linhas:
        return [], []

    cabecalho = [str(valor) if valor is not None else "" for valor in linhas[0]]
    return cabecalho, [list(linha) for linha in linhas[1:]]


def _escrever_bloco(planilha, cabecalho: list[str], linhas: list[list], preenchimento: PatternFill | None) -> None:
    planilha.append(cabecalho)
    for celula in planilha[planilha.max_row]:
        celula.font = Font(bold=True)
        if preenchimento is not None:
            celula.fill = preenchimento

    for linha in linhas:
        planilha.append(linha)
        if preenchimento is not None:
            for celula in planilha[planilha.max_row]:
                celula.fill = preenchimento


def _aplicar_largura_automatica(planilha) -> None:
    for coluna in planilha.columns:
        maior_valor = max((len(str(celula.value)) for celula in coluna if celula.value is not None), default=0)
        planilha.column_dimensions[coluna[0].column_letter].width = min(maior_valor + 2, _LARGURA_MAXIMA_COLUNA)


def juntar_planilhas(conteudo1: bytes, conteudo2: bytes) -> bytes:
    cabecalho1, linhas1 = _ler_planilha(conteudo1)
    cabecalho2, linhas2 = _ler_planilha(conteudo2)

    workbook = Workbook()
    planilha = workbook.active
    planilha.title = "Planilhas combinadas"

    if cabecalho1 and set(cabecalho1) == set(cabecalho2):
        indices = [cabecalho2.index(coluna) for coluna in cabecalho1]
        linhas2_reordenadas = [[linha[indice] for indice in indices] for linha in linhas2]
        _escrever_bloco(planilha, cabecalho1, linhas1 + linhas2_reordenadas, preenchimento=None)
    else:
        _escrever_bloco(planilha, cabecalho1, linhas1, _VERDE_CLARO)
        planilha.append([])
        _escrever_bloco(planilha, cabecalho2, linhas2, _LARANJA_CLARO)

    _aplicar_largura_automatica(planilha)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
