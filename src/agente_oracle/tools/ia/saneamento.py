"""Saneamento de PII/segredo em texto antes de sair pra uma IA fora da
máquina — regex, sem IA nenhuma no meio (barato, determinístico, mesma
saída sempre). Cobre CPF, e-mail, telefone (padrão BR) e trecho parecido
com senha/token.

Não é universal: `tools/ia/cliente_protegido.py` decide, ponto de chamada
por ponto de chamada, se aplica isso ou não — em `deteccao_seguranca.py`
(TI), por exemplo, o identificador da conta é o próprio objeto do achado
de segurança, então não passa por aqui (ver o plano de guardrails)."""

import re

_PADRAO_CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11}\b")
_PADRAO_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# Exige o sufixo "-XXXX" (4 dígitos) pra não confundir com o "-XX" (2
# dígitos) do CPF formatado.
_PADRAO_TELEFONE = re.compile(r"\(?\d{2}\)?[\s-]?9?\d{4}-\d{4}")
_PADRAO_SEGREDO = re.compile(r"(?:senha|password|token)\s*[:=]\s*\S+", re.IGNORECASE)

_MASCARAS = (
    (_PADRAO_SEGREDO, "[SENHA]"),
    (_PADRAO_EMAIL, "[E-MAIL]"),
    (_PADRAO_TELEFONE, "[TELEFONE]"),
    (_PADRAO_CPF, "[CPF]"),
)


def sanitizar_dado_sensivel(texto: str) -> str:
    """Troca CPF/e-mail/telefone/padrão de segredo por uma tag fixa — a IA
    nem precisa do valor real pra julgar um chamado ou currículo. Segredo e
    e-mail saem antes de telefone/CPF de propósito: um token com muito
    dígito seguido não pode acabar mascarado como se fosse CPF."""
    for padrao, mascara in _MASCARAS:
        texto = padrao.sub(mascara, texto)
    return texto


def sanitizar_mensagens(mensagens: list[dict]) -> list[dict]:
    """Aplica `sanitizar_dado_sensivel` no `content` de cada mensagem —
    cobre tanto uma lista curta (`[{"role": "user", ...}]`) quanto um
    histórico inteiro de conversa (ex: `agent/financeiro/financeiro.py`).
    Nunca modifica a lista/dicionários originais."""
    return [{**mensagem, "content": sanitizar_dado_sensivel(mensagem["content"])} for mensagem in mensagens]
