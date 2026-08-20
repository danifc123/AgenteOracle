"""Extração de texto de currículo (PDF/DOCX) — a IA em `agent/rh/analise_curriculo.py`
precisa de texto pra analisar, não do arquivo bruto. `.doc` (formato binário
antigo do Word) fica de fora de propósito: não existe biblioteca pura Python
confiável pra ele (as alternativas exigem `antiword`/LibreOffice instalado
no servidor) — o front (`SeletorArquivoCurriculo`) já só aceita
`.pdf`/`.docx`.

PDF escaneado sem camada de texto (só imagem) também não é suportado —
extrai string vazia, o que vira `ArquivoCurriculoInvalido` aqui. OCR fica
de fora desta leva; se isso virar um problema real de uso, é o próximo
passo natural.
"""

import io

import docx
import pypdf


class ArquivoCurriculoInvalido(Exception):
    """Levantada quando o arquivo não pode virar texto: extensão não
    suportada, arquivo corrompido, ou nenhum texto extraído (ex: PDF
    escaneado sem OCR)."""


def _extrair_docx(conteudo: bytes) -> str:
    try:
        documento = docx.Document(io.BytesIO(conteudo))
    except Exception as erro:
        raise ArquivoCurriculoInvalido(
            "Não consegui ler esse arquivo .docx — ele parece corrompido."
        ) from erro
    return "\n".join(paragrafo.text for paragrafo in documento.paragraphs)


def _extrair_pdf(conteudo: bytes) -> str:
    try:
        leitor = pypdf.PdfReader(io.BytesIO(conteudo))
        return "\n".join(pagina.extract_text() or "" for pagina in leitor.pages)
    except Exception as erro:
        raise ArquivoCurriculoInvalido(
            "Não consegui ler esse arquivo .pdf — ele parece corrompido."
        ) from erro


def extrair_texto(nome_arquivo: str, conteudo: bytes) -> str:
    nome_normalizado = nome_arquivo.lower()

    if nome_normalizado.endswith(".pdf"):
        texto = _extrair_pdf(conteudo)
    elif nome_normalizado.endswith(".docx"):
        texto = _extrair_docx(conteudo)
    else:
        raise ArquivoCurriculoInvalido("Formato de arquivo não suportado — envie um .pdf ou .docx.")

    texto = texto.strip()
    if not texto:
        raise ArquivoCurriculoInvalido(
            "Não encontrei texto nesse arquivo — se for um PDF escaneado (imagem), ainda não conseguimos ler."
        )
    return texto
