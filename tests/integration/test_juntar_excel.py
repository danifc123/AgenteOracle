import io

import pytest
from openpyxl import Workbook

pytestmark = pytest.mark.integration


def _bytes_planilha(cabecalho: list[str], linhas: list[list]) -> bytes:
    workbook = Workbook()
    planilha = workbook.active
    planilha.append(cabecalho)
    for linha in linhas:
        planilha.append(linha)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class TestJuntarExcelRota:
    def test_sem_token_retorna_401(self, mcp_app) -> None:
        arquivo = _bytes_planilha(["nome"], [["Ana"]])
        resposta = mcp_app.post(
            "/api/ferramentas/juntar-excel",
            files={
                "arquivo1": ("a.xlsx", arquivo, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                "arquivo2": ("b.xlsx", arquivo, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            },
        )
        assert resposta.status_code == 401

    def test_upload_valido_retorna_xlsx(self, mcp_app, token_teste) -> None:
        arquivo1 = _bytes_planilha(["nome"], [["Ana"]])
        arquivo2 = _bytes_planilha(["nome"], [["Bruno"]])

        resposta = mcp_app.post(
            "/api/ferramentas/juntar-excel",
            headers={"Authorization": f"Bearer {token_teste}"},
            files={
                "arquivo1": ("a.xlsx", arquivo1, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                "arquivo2": ("b.xlsx", arquivo2, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            },
        )

        assert resposta.status_code == 200
        assert resposta.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert "planilhas_combinadas.xlsx" in resposta.headers["content-disposition"]

    def test_arquivo_faltando_retorna_400(self, mcp_app, token_teste) -> None:
        arquivo1 = _bytes_planilha(["nome"], [["Ana"]])

        resposta = mcp_app.post(
            "/api/ferramentas/juntar-excel",
            headers={"Authorization": f"Bearer {token_teste}"},
            files={
                "arquivo1": ("a.xlsx", arquivo1, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            },
        )
        assert resposta.status_code == 400

    def test_arquivo_corrompido_retorna_400(self, mcp_app, token_teste) -> None:
        arquivo_valido = _bytes_planilha(["nome"], [["Ana"]])

        resposta = mcp_app.post(
            "/api/ferramentas/juntar-excel",
            headers={"Authorization": f"Bearer {token_teste}"},
            files={
                "arquivo1": ("a.xlsx", b"nao e um xlsx valido", "application/octet-stream"),
                "arquivo2": (
                    "b.xlsx",
                    arquivo_valido,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )
        assert resposta.status_code == 400
