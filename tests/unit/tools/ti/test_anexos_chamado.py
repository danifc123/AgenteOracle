import asyncio

from agente_oracle.tools.ti import anexos_chamado as mod
from agente_oracle.tools.ti.glpi import DocumentoAnexo, DocumentoBaixado


class _PaginaFake:
    def __init__(self, texto: str):
        self._texto = texto

    def extract_text(self):
        return self._texto


class _PdfReaderFake:
    def __init__(self, _stream):
        self.is_encrypted = False
        self.pages = [_PaginaFake("Causa raiz: certificado expirado.")]


class _ClienteFake:
    """Fake mínimo do Protocol `ClienteGLPI` — só os dois métodos que
    `extrair_textos_anexos` usa. `conteudos` mapeia `documento_id` pra um
    `DocumentoBaixado`, `None` (download falhou) ou uma `Exception` (pra
    simular erro de rede)."""

    def __init__(self, documentos: list[DocumentoAnexo], conteudos: dict | None = None, falha_listagem: bool = False):
        self._documentos = documentos
        self._conteudos = conteudos or {}
        self._falha_listagem = falha_listagem
        self.baixados: list[int] = []
        self._simultaneos_atual = 0
        self.simultaneos_pico = 0

    async def listar_documentos(self, chamado_id: int) -> list[DocumentoAnexo]:
        if self._falha_listagem:
            raise RuntimeError("GLPI fora do ar")
        return self._documentos

    async def baixar_documento(self, documento_id: int):
        self._simultaneos_atual += 1
        self.simultaneos_pico = max(self.simultaneos_pico, self._simultaneos_atual)
        await asyncio.sleep(0.01)
        self.baixados.append(documento_id)
        self._simultaneos_atual -= 1
        resultado = self._conteudos.get(documento_id)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado


class TestTipoSuportado:
    def test_pdf_por_mime(self):
        assert mod._tipo_suportado("relatorio.pdf", "application/pdf") == "pdf"

    def test_pdf_por_extensao_quando_mime_e_generico(self):
        assert mod._tipo_suportado("relatorio.PDF", "application/octet-stream") == "pdf"

    def test_texto_por_mime(self):
        assert mod._tipo_suportado("log.txt", "text/plain") == "texto"

    def test_log_por_extensao_quando_mime_e_generico(self):
        assert mod._tipo_suportado("servico.log", "application/octet-stream") == "texto"

    def test_imagem_nao_e_suportada(self):
        assert mod._tipo_suportado("print.png", "image/png") is None

    def test_html_nao_e_suportado(self):
        # De propósito fora de escopo — traria de volta o ruído de marcação
        # que `_texto_para_ia` existe pra tirar.
        assert mod._tipo_suportado("pagina.html", "text/html") is None

    def test_csv_nao_e_suportado(self):
        assert mod._tipo_suportado("tabela.csv", "text/csv") is None

    def test_docx_nao_e_suportado(self):
        assert mod._tipo_suportado("curriculo.docx", "application/vnd.openxmlformats") is None


class TestDecodificarTexto:
    def test_utf8_simples(self):
        assert mod._decodificar_texto(b"log de teste") == "log de teste"

    def test_utf8_com_bom(self):
        assert mod._decodificar_texto("log com acentuação".encode("utf-8-sig")) == "log com acentuação"

    def test_cp1252_com_acentuacao(self):
        conteudo = "não conseguiu emitir a nota".encode("cp1252")
        assert mod._decodificar_texto(conteudo) == "não conseguiu emitir a nota"

    def test_utf16_com_bom_tipico_do_powershell(self):
        conteudo = "log gerado pelo powershell".encode("utf-16")
        assert mod._decodificar_texto(conteudo) == "log gerado pelo powershell"

    def test_binario_com_nul_devolve_none(self):
        assert mod._decodificar_texto(b"\x00\x01\x02binario") is None

    def test_vazio_ou_so_espaco_devolve_none(self):
        assert mod._decodificar_texto(b"   \n  ") is None


class TestExtrairPdf:
    def test_extrai_texto_das_paginas(self, monkeypatch):
        monkeypatch.setattr(mod.pypdf, "PdfReader", _PdfReaderFake)
        assert mod._extrair_pdf(b"conteudo") == "Causa raiz: certificado expirado."

    def test_pdf_corrompido_devolve_none_sem_levantar(self):
        assert mod._extrair_pdf(b"lixo-isso-nao-e-um-pdf-de-verdade") is None

    def test_pdf_criptografado_devolve_none(self, monkeypatch):
        class _ReaderCriptografado:
            def __init__(self, _stream):
                self.is_encrypted = True
                self.pages = []

        monkeypatch.setattr(mod.pypdf, "PdfReader", _ReaderCriptografado)
        assert mod._extrair_pdf(b"conteudo") is None

    def test_pdf_escaneado_sem_camada_de_texto_devolve_none(self, monkeypatch):
        class _ReaderVazio:
            def __init__(self, _stream):
                self.is_encrypted = False
                self.pages = [_PaginaFake("")]

        monkeypatch.setattr(mod.pypdf, "PdfReader", _ReaderVazio)
        assert mod._extrair_pdf(b"conteudo") is None

    def test_para_de_ler_paginas_depois_de_bater_o_limite(self, monkeypatch):
        class _PaginaQueExplode:
            def extract_text(self):
                raise AssertionError("não deveria ler essa página — já passou do limite de caracteres")

        class _ReaderComMuitasPaginas:
            def __init__(self, _stream):
                self.is_encrypted = False
                pagina_grande = _PaginaFake("x" * mod.MAX_CARACTERES_CONTEUDO)
                self.pages = [pagina_grande, _PaginaQueExplode()]

        monkeypatch.setattr(mod.pypdf, "PdfReader", _ReaderComMuitasPaginas)
        assert mod._extrair_pdf(b"conteudo") is not None


class TestTruncar:
    def test_nao_trunca_dentro_do_limite(self):
        texto, truncado = mod._truncar("curto", "pdf")
        assert texto == "curto"
        assert truncado is False

    def test_exatamente_no_limite_nao_trunca(self):
        texto_exato = "A" * mod.MAX_CARACTERES_CONTEUDO
        _texto, truncado = mod._truncar(texto_exato, "pdf")
        assert truncado is False

    def test_pdf_mantem_o_inicio(self):
        grande = "A" * (mod.MAX_CARACTERES_CONTEUDO + 100)
        texto, truncado = mod._truncar(grande, "pdf")
        assert texto == grande[: mod.MAX_CARACTERES_CONTEUDO]
        assert truncado is True

    def test_log_mantem_o_fim(self):
        grande = "ruido-de-inicializacao " * 300 + "ERRO FATAL: certificado expirado"
        texto, truncado = mod._truncar(grande, "texto")
        assert texto == grande[-mod.MAX_CARACTERES_CONTEUDO :]
        assert texto.endswith("ERRO FATAL: certificado expirado")
        assert truncado is True


class TestTextoDoDocumento:
    def test_pdf_suportado_devolve_textoanexo(self, monkeypatch):
        monkeypatch.setattr(mod.pypdf, "PdfReader", _PdfReaderFake)
        resultado = mod.texto_do_documento("relatorio.pdf", "application/pdf", b"conteudo")
        assert resultado.nome_arquivo == "relatorio.pdf"
        assert "certificado expirado" in resultado.texto
        assert resultado.truncado is False

    def test_texto_simples_devolve_textoanexo(self):
        resultado = mod.texto_do_documento("log.txt", "text/plain", b"linha de log")
        assert resultado.texto == "linha de log"

    def test_imagem_devolve_none(self):
        assert mod.texto_do_documento("print.png", "image/png", b"bytes-de-imagem") is None

    def test_pdf_corrompido_devolve_none(self):
        assert mod.texto_do_documento("relatorio.pdf", "application/pdf", b"lixo") is None


class TestExtrairTextosAnexos:
    async def test_listagem_falhando_devolve_lista_vazia(self):
        cliente = _ClienteFake(documentos=[], falha_listagem=True)
        assert await mod.extrair_textos_anexos(cliente, 1) == []

    async def test_ignora_tipo_nao_suportado_sem_tentar_baixar(self):
        documentos = [DocumentoAnexo(id=1, nome_arquivo="print.png", mime="image/png")]
        cliente = _ClienteFake(documentos=documentos)

        resultado = await mod.extrair_textos_anexos(cliente, 1)

        assert resultado == []
        assert cliente.baixados == []

    async def test_baixa_e_extrai_pdf_e_texto(self, monkeypatch):
        monkeypatch.setattr(mod.pypdf, "PdfReader", _PdfReaderFake)
        documentos = [
            DocumentoAnexo(id=1, nome_arquivo="relatorio.pdf", mime="application/pdf"),
            DocumentoAnexo(id=2, nome_arquivo="log.txt", mime="text/plain"),
        ]
        conteudos = {
            1: DocumentoBaixado(conteudo=b"pdf", content_type="application/pdf"),
            2: DocumentoBaixado(conteudo=b"linha de log", content_type="text/plain"),
        }
        cliente = _ClienteFake(documentos=documentos, conteudos=conteudos)

        resultado = await mod.extrair_textos_anexos(cliente, 1)

        assert {texto.nome_arquivo for texto in resultado} == {"relatorio.pdf", "log.txt"}

    async def test_download_falhando_num_anexo_nao_impede_os_outros(self, monkeypatch):
        monkeypatch.setattr(mod.pypdf, "PdfReader", _PdfReaderFake)
        documentos = [
            DocumentoAnexo(id=1, nome_arquivo="relatorio.pdf", mime="application/pdf"),
            DocumentoAnexo(id=2, nome_arquivo="log.txt", mime="text/plain"),
        ]
        conteudos = {
            1: RuntimeError("timeout baixando"),
            2: DocumentoBaixado(conteudo=b"linha de log", content_type="text/plain"),
        }
        cliente = _ClienteFake(documentos=documentos, conteudos=conteudos)

        resultado = await mod.extrair_textos_anexos(cliente, 1)

        assert len(resultado) == 1
        assert resultado[0].nome_arquivo == "log.txt"

    async def test_baixar_documento_devolvendo_none_e_pulado(self):
        documentos = [DocumentoAnexo(id=1, nome_arquivo="log.txt", mime="text/plain")]
        cliente = _ClienteFake(documentos=documentos, conteudos={1: None})

        assert await mod.extrair_textos_anexos(cliente, 1) == []

    async def test_mais_de_3_anexos_so_le_os_3_primeiros(self):
        documentos = [DocumentoAnexo(id=i, nome_arquivo=f"log{i}.txt", mime="text/plain") for i in range(1, 6)]
        conteudos = {
            i: DocumentoBaixado(conteudo=f"log {i}".encode(), content_type="text/plain") for i in range(1, 6)
        }
        cliente = _ClienteFake(documentos=documentos, conteudos=conteudos)

        resultado = await mod.extrair_textos_anexos(cliente, 1)

        assert len(resultado) == 3
        assert len(cliente.baixados) == 3

    async def test_downloads_respeitam_o_teto_de_simultaneos(self):
        documentos = [DocumentoAnexo(id=i, nome_arquivo=f"log{i}.txt", mime="text/plain") for i in range(1, 4)]
        conteudos = {
            i: DocumentoBaixado(conteudo=f"log {i}".encode(), content_type="text/plain") for i in range(1, 4)
        }
        cliente = _ClienteFake(documentos=documentos, conteudos=conteudos)

        await mod.extrair_textos_anexos(cliente, 1)

        assert cliente.simultaneos_pico <= mod._MAX_DOWNLOADS_SIMULTANEOS


class TestMontarBlocoAnexos:
    def test_lista_vazia_devolve_string_vazia(self):
        assert mod.montar_bloco_anexos([]) == ""

    def test_formata_com_marcador_de_nome(self):
        bloco = mod.montar_bloco_anexos(
            [mod.TextoAnexo(nome_arquivo="log.txt", texto="conteudo do log", truncado=False)]
        )
        assert "[Anexo: log.txt]" in bloco
        assert "conteudo do log" in bloco
        assert "[Fim do anexo]" in bloco

    def test_truncado_mostra_aviso(self):
        bloco = mod.montar_bloco_anexos([mod.TextoAnexo(nome_arquivo="log.txt", texto="x", truncado=True)])
        assert "truncado" in bloco.lower()

    def test_varios_anexos_aparecem_todos(self):
        textos = [
            mod.TextoAnexo(nome_arquivo="a.txt", texto="conteudo a", truncado=False),
            mod.TextoAnexo(nome_arquivo="b.pdf", texto="conteudo b", truncado=False),
        ]
        bloco = mod.montar_bloco_anexos(textos)
        assert "a.txt" in bloco
        assert "b.pdf" in bloco
