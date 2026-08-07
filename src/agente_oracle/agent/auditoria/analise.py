"""Análise genérica de qualidade de dados — não sabe SQL nem conhece nenhum
módulo específico, só recebe `PerfilCampo` já prontos (ver
`agent/auditoria/perfil_campo.py`) e pede pra IA apontar valores que parecem
fora do padrão. A IA decide livremente o que é anômalo (não há regra fixa
tipo z-score aqui), mas todo achado passa por uma checagem determinística
(`_achado_fundamentado`) antes de ser devolvido — mesmo espírito da rede de
segurança em `agent/financeiro/financeiro.py`
(`_valores_monetarios_no_texto`/`_valores_numericos_do_resultado`): nunca
confiar que um valor citado pela IA é real sem conferir contra o dado que
foi de fato mandado pra ela."""

import json
from dataclasses import dataclass, replace

from ollama import AsyncClient

from agente_oracle.agent.auditoria.perfil_campo import PerfilCampo

# Mesma constante usada em financeiro.py/projecoes.py — evita reservar mais
# RAM do que o prompt (perfis + achados) precisa.
_OPCOES_OLLAMA = {"num_ctx": 16384}

_ACHADOS_SCHEMA = {
    "type": "object",
    "properties": {
        "achados": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "modulo": {"type": "string"},
                    "view": {"type": "string"},
                    "campo": {"type": "string"},
                    "valor": {"type": "string"},
                    "descricao": {"type": "string"},
                },
                "required": ["modulo", "view", "campo", "valor", "descricao"],
            },
        }
    },
    "required": ["achados"],
}

_PROMPT_SISTEMA = (
    "Você é um auditor de qualidade de dados. Você recebe, para cada campo de cada view de um "
    "sistema, os valores mais frequentes daquele campo e quantas vezes cada um ocorre. Sua tarefa "
    "é apontar valores que parecem estar fora do padrão predominante do campo — por exemplo um "
    "código com uma quantidade de dígitos muito diferente dos demais, uma sigla que não tem 2 "
    "letras quando as outras têm, um valor com formato claramente diferente da maioria. "
    "Não aponte o valor mais comum de um campo, nem valores plausíveis só porque são pouco "
    "frequentes — frequência baixa sozinha não é motivo. Se nada em um perfil parecer fora do "
    "padrão, simplesmente não gere achado para ele; é normal a lista de achados vir vazia. "
    "Cite em `valor` exatamente um dos valores que você recebeu, caractere por caractere — nunca "
    "invente, corrija ou arredonde um valor. Escreva `descricao` em português, uma frase curta, "
    "no formato 'Analise o campo <campo> na filial/cliente/fornecedor/registro <valor>, ele parece "
    "estar fora do padrão' — adapte a frase ao que o campo representa."
)


@dataclass(frozen=True)
class Achado:
    modulo: str
    view: str
    campo: str
    valor: str
    descricao: str


async def analisar_perfis(ollama_client: AsyncClient, modelo: str, perfis: list[PerfilCampo]) -> list[Achado]:
    """Pede à IA que analise os perfis recebidos e aponte o que parece fora
    do padrão. Nunca deixa a chamada quebrar: qualquer falha do Ollama,
    resposta vazia ou mal formada devolve lista vazia — o painel simplesmente
    mostra "nenhum achado" nesse caso."""
    # Perfis sem nenhum valor (view/campo sem registro) não têm o que
    # comparar — `max()` na linha abaixo quebraria com sequência vazia.
    perfis = [perfil for perfil in perfis if perfil.valores]
    if not perfis:
        return []

    perfis_por_chave = {
        (perfil.modulo, perfil.view, perfil.campo): (
            {valor for valor, _ in perfil.valores},
            max(perfil.valores, key=lambda item: item[1])[0],
        )
        for perfil in perfis
    }

    try:
        resposta = await ollama_client.chat(
            model=modelo,
            messages=[
                {"role": "system", "content": _PROMPT_SISTEMA},
                {"role": "user", "content": _perfis_para_texto(perfis)},
            ],
            format=_ACHADOS_SCHEMA,
            options=_OPCOES_OLLAMA,
        )
        corpo = json.loads(resposta.message.content or "{}")
    except Exception:
        # Best-effort: chamada de IA (erro de rede/timeout do Ollama) ou
        # resposta que não veio em JSON válido — a auditoria segue sem
        # achados em vez de derrubar a análise inteira por causa da IA.
        return []

    achados_brutos = corpo.get("achados")
    if not isinstance(achados_brutos, list):
        return []

    return [
        Achado(
            modulo=achado["modulo"],
            view=achado["view"],
            campo=achado["campo"],
            valor=achado["valor"],
            descricao=achado["descricao"],
        )
        for achado in achados_brutos
        if _achado_valido(achado) and _achado_fundamentado(achado, perfis_por_chave)
    ]


def _achado_fundamentado(
    achado: dict, perfis_por_chave: dict[tuple[str, str, str], tuple[set[str], str]]
) -> bool:
    """Descarta achados que citam um `(modulo, view, campo)` que não estava
    entre os perfis realmente enviados, ou um `valor` que não está entre os
    valores daquele perfil específico — valida a tupla inteira, não só o
    valor isolado, senão a IA poderia citar um valor real de um perfil e
    prendê-lo a um `(view, campo)` errado. Também descarta o valor mais
    frequente do perfil (quando há mais de um valor distinto): um achado
    "isso é fora do padrão" citando o valor mais comum é quase sempre um
    non-sequitur — filtro barato, não substitui a checagem semântica real."""
    chave = (achado["modulo"], achado["view"], achado["campo"])
    entrada = perfis_por_chave.get(chave)
    if entrada is None:
        return False

    valores_validos, valor_mais_comum = entrada
    valor = achado["valor"]
    if valor not in valores_validos:
        return False
    return not (len(valores_validos) > 1 and valor == valor_mais_comum)


def _achado_valido(achado: object) -> bool:
    return isinstance(achado, dict) and all(
        isinstance(achado.get(campo), str) and achado.get(campo)
        for campo in ("modulo", "view", "campo", "valor", "descricao")
    )


def _perfis_para_texto(perfis: list[PerfilCampo]) -> str:
    blocos = []
    for perfil in perfis:
        valores_texto = ", ".join(f"'{valor}' ({ocorrencias}x)" for valor, ocorrencias in perfil.valores)
        blocos.append(
            f"Módulo: {perfil.modulo} | View: {perfil.view} | Campo: {perfil.campo}\nValores: {valores_texto}"
        )
    return "\n\n".join(blocos)


def filtrar_valores_conhecidos(
    perfis: list[PerfilCampo], valores_conhecidos: set[tuple[str, str, str, str]]
) -> list[PerfilCampo]:
    """Remove de cada perfil os valores cuja tupla `(modulo, view, campo,
    valor)` já está em `valores_conhecidos` — usada tanto pra não gastar uma
    chamada de IA "redescobrindo" um problema já identificado antes (ver
    `tools/auditoria/historico.ja_identificados`) quanto, potencialmente, pra
    qualquer outro conjunto de exclusão no mesmo formato. Se o dado mudou
    desde então (mesmo que continue errado, com um valor diferente), a tupla
    é outra e não é removida — só evita repetir o que já é sabido. Perfil que
    fica sem nenhum valor depois do filtro é descartado inteiro; se todos os
    perfis ficarem vazios, `analisar_perfis` nem chega a chamar o Ollama."""
    perfis_filtrados = []
    for perfil in perfis:
        valores_restantes = tuple(
            (valor, ocorrencias)
            for valor, ocorrencias in perfil.valores
            if (perfil.modulo, perfil.view, perfil.campo, valor) not in valores_conhecidos
        )
        if valores_restantes:
            perfis_filtrados.append(replace(perfil, valores=valores_restantes))
    return perfis_filtrados
