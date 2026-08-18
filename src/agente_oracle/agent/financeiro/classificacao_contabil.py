"""Classificação Contábil — achados de lançamento sem conta definida.

Mesma arquitetura de sempre neste projeto: um passo determinístico acha
CANDIDATOS reais (nunca a IA "procurando" sozinha) — aqui nem precisa de
IA de verdade: a sugestão vem por semelhança de texto do `historico`
contra os lançamentos JÁ classificados, mesmo princípio de fundamentação
de `despesas_suspeitas.py` (só sugere uma conta que já foi usada de
verdade pra um histórico parecido, nunca inventa código de conta). 100%
determinístico — `historico` segue um padrão bem previsível (confirmado
na amostra real: "BX.PAG. 0 /000000254/ -BRASILSEG...", só o número do
documento muda de lançamento pra lançamento).

Confirmado direto no STAGE antes de escrever isto: de 2.399.918
lançamentos ativos, 658.950 (27%) têm CONTA = '-1' — fila real de
trabalho, não um cenário hipotético (ver comentário em
`db/views/financeiro_science.sql::vw_lancamentos_contabeis`). Vale
confirmar com o time de controladoria o significado exato de `-1` antes
de confiar cegamente na sugestão em produção (ver plano)."""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date

_LIMIAR_CONFIANCA = 0.9
_SUPORTE_MINIMO = 3
_CONTA_NAO_DEFINIDA = "-1"

_SEQUENCIA_DIGITOS_REGEX = re.compile(r"\d+")


@dataclass(frozen=True)
class LancamentoContabil:
    documento: str
    linha: str
    conta: str
    conta_descricao: str | None
    historico: str
    valor: float
    data_movimentacao: date


@dataclass(frozen=True)
class SugestaoClassificacao:
    documento: str
    linha: str
    historico: str
    valor: float
    data_movimentacao: date
    conta_sugerida: str
    conta_descricao_sugerida: str | None
    confianca_percentual: float
    suporte_historico: int


def _chave_historico(historico: str) -> str:
    """Normaliza o histórico pra agrupar por "formato", ignorando o que
    varia de lançamento pra lançamento (número de documento, valor) —
    maiúsculo, sem acento, sequências de dígito colapsadas num único
    marcador (`#`)."""
    sem_acento = unicodedata.normalize("NFKD", historico).encode("ascii", "ignore").decode("ascii")
    sem_digitos = _SEQUENCIA_DIGITOS_REGEX.sub("#", sem_acento.upper())
    return " ".join(sem_digitos.split())


def construir_dicionario(classificados: list[LancamentoContabil]) -> dict[str, Counter]:
    """chave de histórico normalizada -> contagem de conta usada — só
    considera lançamento com conta de verdade (exclui `-1`)."""
    dicionario: dict[str, Counter] = {}
    for lancamento in classificados:
        if lancamento.conta == _CONTA_NAO_DEFINIDA:
            continue
        chave = _chave_historico(lancamento.historico)
        dicionario.setdefault(chave, Counter())[lancamento.conta] += 1
    return dicionario


def mapa_conta_descricao(classificados: list[LancamentoContabil]) -> dict[str, str]:
    """conta -> descrição, a partir dos próprios lançamentos classificados
    (a descrição é propriedade da conta, não do lançamento — qualquer
    ocorrência serve)."""
    mapa: dict[str, str] = {}
    for lancamento in classificados:
        if lancamento.conta != _CONTA_NAO_DEFINIDA and lancamento.conta_descricao:
            mapa.setdefault(lancamento.conta, lancamento.conta_descricao)
    return mapa


def sugerir_classificacoes(
    nao_classificados: list[LancamentoContabil],
    dicionario: dict[str, Counter],
    descricoes: dict[str, str],
) -> list[SugestaoClassificacao]:
    """Pra cada lançamento sem conta, olha a chave normalizada do
    histórico no dicionário: só sugere quando a conta majoritária daquela
    chave atinge `_LIMIAR_CONFIANCA` E tem `_SUPORTE_MINIMO` precedentes —
    senão não aparece no resultado (mais honesto que forçar um palpite
    fraco). Ordenado por maior valor absoluto primeiro (o que tem mais
    impacto financeiro revisar primeiro)."""
    sugestoes = []
    for lancamento in nao_classificados:
        contagem = dicionario.get(_chave_historico(lancamento.historico))
        if not contagem:
            continue

        total = sum(contagem.values())
        if total < _SUPORTE_MINIMO:
            continue

        conta_majoritaria, ocorrencias = contagem.most_common(1)[0]
        confianca = ocorrencias / total
        if confianca < _LIMIAR_CONFIANCA:
            continue

        sugestoes.append(
            SugestaoClassificacao(
                documento=lancamento.documento,
                linha=lancamento.linha,
                historico=lancamento.historico,
                valor=lancamento.valor,
                data_movimentacao=lancamento.data_movimentacao,
                conta_sugerida=conta_majoritaria,
                conta_descricao_sugerida=descricoes.get(conta_majoritaria),
                confianca_percentual=round(confianca * 100, 1),
                suporte_historico=total,
            )
        )

    sugestoes.sort(key=lambda sugestao: abs(sugestao.valor), reverse=True)
    return sugestoes
