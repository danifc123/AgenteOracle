import io
from collections.abc import Sequence

from openpyxl import Workbook
from openpyxl.styles import Font


def gerar_xlsx(cabecalho: Sequence[str], linhas: Sequence[Sequence], titulo: str = "Relatório") -> bytes:
    """Monta um arquivo Excel (.xlsx) em memória com cabeçalho em negrito e
    largura de coluna automática, no formato usado por todos os relatórios
    (gerados por tool fixa ou pela IA no chat)."""
    workbook = Workbook()
    planilha = workbook.active
    planilha.title = titulo

    planilha.append(list(cabecalho))
    for celula in planilha[1]:
        celula.font = Font(bold=True)

    for linha in linhas:
        planilha.append(list(linha))

    for coluna in planilha.columns:
        maior_valor = max((len(str(celula.value)) for celula in coluna if celula.value is not None), default=0)
        planilha.column_dimensions[coluna[0].column_letter].width = min(maior_valor + 2, 50)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
