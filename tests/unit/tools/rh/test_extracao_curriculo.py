import pytest

from agente_oracle.tools.rh import extracao_curriculo as mod


class _PaginaFake:
    def __init__(self, texto: str):
        self._texto = texto

    def extract_text(self):
        return self._texto


class _PdfReaderFake:
    def __init__(self, _stream):
        self.pages = [_PaginaFake("João da Silva\nExperiência em agronegócio.")]


class _ParagrafoFake:
    def __init__(self, texto: str):
        self.text = texto


class _DocumentoFake:
    def __init__(self, _stream):
        self.paragraphs = [_ParagrafoFake("João da Silva"), _ParagrafoFake("Experiência em agronegócio.")]


def _levantar_erro(_stream):
    raise ValueError("arquivo corrompido")


class TestExtrairTexto:
    def test_pdf_extrai_texto_das_paginas(self, monkeypatch):
        monkeypatch.setattr(mod.pypdf, "PdfReader", _PdfReaderFake)
        texto = mod.extrair_texto("curriculo.pdf", b"conteudo qualquer")
        assert "João da Silva" in texto

    def test_docx_extrai_texto_dos_paragrafos(self, monkeypatch):
        monkeypatch.setattr(mod.docx, "Document", _DocumentoFake)
        texto = mod.extrair_texto("curriculo.docx", b"conteudo qualquer")
        assert "João da Silva" in texto

    def test_extensao_case_insensitive(self, monkeypatch):
        monkeypatch.setattr(mod.pypdf, "PdfReader", _PdfReaderFake)
        texto = mod.extrair_texto("CURRICULO.PDF", b"conteudo qualquer")
        assert texto

    def test_extensao_nao_suportada_levanta_erro(self):
        with pytest.raises(mod.ArquivoCurriculoInvalido):
            mod.extrair_texto("curriculo.doc", b"conteudo qualquer")

    def test_pdf_corrompido_levanta_erro(self, monkeypatch):
        monkeypatch.setattr(mod.pypdf, "PdfReader", _levantar_erro)
        with pytest.raises(mod.ArquivoCurriculoInvalido):
            mod.extrair_texto("curriculo.pdf", b"lixo")

    def test_docx_corrompido_levanta_erro(self, monkeypatch):
        monkeypatch.setattr(mod.docx, "Document", _levantar_erro)
        with pytest.raises(mod.ArquivoCurriculoInvalido):
            mod.extrair_texto("curriculo.docx", b"lixo")

    def test_pdf_sem_texto_levanta_erro(self, monkeypatch):
        class _ReaderVazio:
            def __init__(self, _stream):
                self.pages = [_PaginaFake("")]

        monkeypatch.setattr(mod.pypdf, "PdfReader", _ReaderVazio)
        with pytest.raises(mod.ArquivoCurriculoInvalido):
            mod.extrair_texto("curriculo.pdf", b"conteudo")
