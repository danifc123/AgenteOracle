"""Texto de anexo (PDF, .txt/.log) como contexto extra pra avaliação de
suficiência de um chamado — pedido do Pablo (infra), 2026-10-01, depois
de confirmar ao vivo (chamado real #3360, GLPI homologação) que a IA de
triagem ignora TODO anexo hoje, não importa o tipo (`server/ti/
chamados.py::_texto_para_ia` descarta a tag `<img>` da descrição, e
anexo pelo botão de clipe nem aparece ali). Imagem fica de fora de
propósito (decisão do chefe/Pablo: visão é evolução futura, ver
`visao_imagens_chamados_futuro` no roteiro) — por isso a descoberta
abaixo nunca baixa um anexo de imagem, filtra pelo tipo ANTES do
download.

Fica fora de `agent/` de propósito — isso é só concatenação de texto
puro na descrição (`server/ti/chamados.py::processar_chamado_novo` soma
`montar_bloco_anexos(...)` na descrição ANTES de chamar
`avaliar_chamado`), não um formato de mensagem multimodal novo; esse
módulo não precisa saber nada de IA."""

import asyncio
import io
from dataclasses import dataclass
from typing import Literal

import pypdf

from agente_oracle.agent.core import MAX_CARACTERES_CONTEUDO
from agente_oracle.tools.ti.glpi import ClienteGLPI, DocumentoAnexo

# Chamado raramente tem mais que isso, e cada anexo já limitado a
# MAX_CARACTERES_CONTEUDO mantém o custo (tokens) sob controle — folga
# confortável dentro do `num_ctx=16384` do Ollama (`agent/core.py`).
_MAX_ANEXOS_LIDOS = 3
# Cada `baixar_documento` abre sua PRÓPRIA sessão na API Legada do GLPI —
# sem limitar, um chamado com vários anexos abriria várias sessões
# simultâneas com a mesma conta de serviço.
_MAX_DOWNLOADS_SIMULTANEOS = 2
_EXTENSOES_TEXTO = (".txt", ".log")
_EXTENSAO_PDF = ".pdf"

_TipoAnexo = Literal["pdf", "texto"]


@dataclass(frozen=True)
class TextoAnexo:
    nome_arquivo: str
    texto: str
    truncado: bool


def _tipo_suportado(nome_arquivo: str, mime: str) -> _TipoAnexo | None:
    """PDF e texto por mime OU extensão — o GLPI às vezes guarda o
    arquivo como `application/octet-stream` genérico, sobra só o nome pra
    decidir. Exclui `text/html`/`text/csv` de propósito: não foi pedido,
    e HTML traria de volta o ruído de marcação que `_texto_para_ia`
    existe pra tirar. Imagem nunca passa daqui — por isso nunca é
    baixada (ver `extrair_textos_anexos`)."""
    nome = nome_arquivo.lower()
    if mime == "application/pdf" or nome.endswith(_EXTENSAO_PDF):
        return "pdf"
    if mime == "text/plain" or nome.endswith(_EXTENSOES_TEXTO):
        return "texto"
    return None


def _decodificar_texto(conteudo: bytes) -> str | None:
    """NUL byte nos primeiros bytes normalmente é binário — EXCETO um BOM
    de UTF-16 (`> arquivo.txt` do PowerShell grava assim por padrão no
    Windows), que também tem NUL byte entre cada caractere ASCII mas é
    texto de verdade. Sem BOM reconhecido, tenta UTF-8 e cai pra cp1252
    (logs do Windows/Protheus não são raros nessa codificação)."""
    amostra = conteudo[:8192]
    if conteudo[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            texto = conteudo.decode("utf-16")
        except UnicodeDecodeError:
            return None
    elif b"\x00" in amostra:
        return None
    else:
        try:
            texto = conteudo.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = conteudo.decode("cp1252", errors="replace")
    texto = texto.replace("\r\n", "\n").strip()
    return texto or None


def _extrair_pdf(conteudo: bytes) -> str | None:
    """Mesmo núcleo de `tools/rh/extracao_curriculo.py::_extrair_pdf`
    (`pypdf.PdfReader` + `extract_text()` por página), mas devolve `None`
    em vez de levantar — um anexo ilegível não pode derrubar a avaliação
    do chamado inteiro, então não duplica a exceção
    `ArquivoCurriculoInvalido` daquele módulo (camada errada pra importar
    daqui, RH é outro domínio). Para de ler página assim que bate
    `MAX_CARACTERES_CONTEUDO` — um manual de 300 páginas não precisa ser
    extraído inteiro só pra ser truncado depois. PDF criptografado sem
    senha e PDF escaneado sem camada de texto também viram `None` — mesma
    limitação (sem OCR) já aceita no módulo de RH."""
    try:
        leitor = pypdf.PdfReader(io.BytesIO(conteudo))
        if leitor.is_encrypted:
            return None
        partes = []
        total = 0
        for pagina in leitor.pages:
            texto_pagina = pagina.extract_text() or ""
            partes.append(texto_pagina)
            total += len(texto_pagina)
            if total >= MAX_CARACTERES_CONTEUDO:
                break
        texto = "\n".join(partes).strip()
        return texto or None
    except Exception:
        return None


def _truncar(texto: str, tipo: _TipoAnexo) -> tuple[str, bool]:
    """PDF mantém o INÍCIO (resumo/causa raiz costuma vir primeiro); log
    mantém o FIM (erro fatal costuma ser a última linha, início de log é
    ruído de inicialização)."""
    if len(texto) <= MAX_CARACTERES_CONTEUDO:
        return texto, False
    if tipo == "pdf":
        return texto[:MAX_CARACTERES_CONTEUDO], True
    return texto[-MAX_CARACTERES_CONTEUDO:], True


def texto_do_documento(nome_arquivo: str, mime: str, conteudo: bytes) -> TextoAnexo | None:
    """Puro, síncrono, nunca levanta — `None` pra tipo não suportado
    (imagem, etc.), conteúdo corrompido, ou vazio depois de extraído."""
    tipo = _tipo_suportado(nome_arquivo, mime)
    if tipo is None:
        return None
    texto_bruto = _extrair_pdf(conteudo) if tipo == "pdf" else _decodificar_texto(conteudo)
    if not texto_bruto:
        return None
    texto, truncado = _truncar(texto_bruto, tipo)
    return TextoAnexo(nome_arquivo=nome_arquivo, texto=texto, truncado=truncado)


async def extrair_textos_anexos(cliente: ClienteGLPI, chamado_id: int) -> list[TextoAnexo]:
    """Nunca levanta — GLPI fora do ar, anexo corrompido, download que
    falhou: cada etapa degrada pulando aquele anexo, nunca interrompe a
    avaliação do chamado inteiro. Filtra por tipo suportado ANTES de
    baixar (imagem nunca é baixada — é o anexo mais comum, economiza a
    chamada de verdade), limita a `_MAX_ANEXOS_LIDOS`, baixa em paralelo
    sob um semáforo (`_MAX_DOWNLOADS_SIMULTANEOS`), e extrai o texto de
    cada um em thread separada (`pypdf` é síncrono e pesado, não pode
    travar o loop de eventos que também serve as rotas HTTP)."""
    try:
        documentos = await cliente.listar_documentos(chamado_id)
    except Exception:
        return []

    candidatos = [doc for doc in documentos if _tipo_suportado(doc.nome_arquivo, doc.mime) is not None]
    candidatos = candidatos[:_MAX_ANEXOS_LIDOS]
    if not candidatos:
        return []

    semaforo = asyncio.Semaphore(_MAX_DOWNLOADS_SIMULTANEOS)

    async def _baixar_e_extrair(documento: DocumentoAnexo) -> TextoAnexo | None:
        try:
            async with semaforo:
                baixado = await cliente.baixar_documento(documento.id)
            if baixado is None:
                return None
            return await asyncio.to_thread(
                texto_do_documento, documento.nome_arquivo, documento.mime, baixado.conteudo
            )
        except Exception:
            return None

    resultados = await asyncio.gather(*(_baixar_e_extrair(documento) for documento in candidatos))
    return [texto for texto in resultados if texto is not None]


def montar_bloco_anexos(textos: list[TextoAnexo]) -> str:
    """`''` quando não há nada extraído; senão um bloco por anexo com
    marcador de início/fim e nome do arquivo, pra IA distinguir "isso é o
    anexo X" de "isso é a descrição digitada pela pessoa" — e um aviso
    textual quando o conteúdo foi truncado, pra IA não tratar um log
    cortado como se fosse o registro completo."""
    blocos = []
    for texto in textos:
        aviso = " (conteúdo truncado)" if texto.truncado else ""
        blocos.append(f"\n\n[Anexo: {texto.nome_arquivo}]{aviso}\n{texto.texto}\n[Fim do anexo]")
    return "".join(blocos)
