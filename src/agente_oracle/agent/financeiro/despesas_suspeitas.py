"""Auditoria Inteligente de Despesas — mesma arquitetura de sempre neste
projeto: um passo determinístico acha CANDIDATOS reais (nunca a IA
"procurando" sozinha), e a IA só julga/descreve o que já foi encontrado.
Diferente de `agent/auditoria/analise.py` (que compara VALOR de um campo
contra a distribuição do próprio campo), aqui o candidato é um GRUPO de
linhas de `vw_titulos_pagar` — não cabe no formato `PerfilCampo`/`Achado`
genérico, por isso este módulo tem o formato próprio (mesmo espírito de
`agent/ti/deteccao_seguranca.py`, que também não força o achado genérico).

Dois tipos de candidato, dois algoritmos determinísticos:
- **Duplicidade**: mesmo fornecedor + mesmo valor + documentos diferentes,
  emitidos numa janela curta de dias — janela curta de propósito, pra não
  confundir cobrança recorrente mensal (aluguel, assinatura) com
  duplicidade real.
- **Anomalia de valor**: valor muito acima da média/desvio-padrão da
  mesma natureza financeira (categoria de despesa), só considerando
  grupo com tamanho mínimo pra estatística fazer sentido.

Se o Ollama falhar ou responder algo mal formado, a análise NÃO esconde
os candidatos — devolve eles com uma descrição genérica (calculada, não
da IA) em vez de lista vazia, porque aqui o candidato já é 100% real
antes de qualquer chamada de IA (diferente da auditoria genérica, onde
o "achado" só existe depois do julgamento da IA)."""

import statistics
from dataclasses import dataclass
from datetime import date, timedelta

from ollama import AsyncClient

from agente_oracle.agent.core import OPCOES_OLLAMA_PADRAO, resposta_json_como_dict
from agente_oracle.db.connection import get_connection
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

_JANELA_DIAS_DUPLICIDADE = 10
_LIMIAR_DESVIOS_PADRAO = 3.0
_TAMANHO_MINIMO_GRUPO_ANOMALIA = 5

_SCHEMA = {
    "type": "object",
    "properties": {
        "achados": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fornecedor_codigo": {"type": "string"},
                    "valor_original": {"type": "number"},
                    "tipo": {"type": "string", "enum": ["duplicidade", "anomalia_valor"]},
                    "descricao": {"type": "string"},
                },
                "required": ["fornecedor_codigo", "valor_original", "tipo", "descricao"],
            },
        }
    },
    "required": ["achados"],
}

_PROMPT_SISTEMA = (
    "Você é um auditor financeiro. Você recebe candidatos JÁ IDENTIFICADOS por um sistema "
    "determinístico: possíveis duplicidades de título a pagar (mesmo fornecedor, mesmo valor, "
    "datas de emissão próximas) e valores muito acima da média da natureza financeira. Sua tarefa "
    "é revisar cada candidato e decidir se ele realmente parece um problema — descarte um "
    "candidato se o nome da natureza sugerir que é uma cobrança recorrente legítima (ex: aluguel, "
    "mensalidade, assinatura) ou se não houver nada de fato suspeito nele. Para cada candidato que "
    "mantiver, escreva uma descrição curta e específica em português explicando o motivo. Copie "
    "`fornecedor_codigo` e `valor_original` exatamente como foram informados — nunca invente um "
    "candidato que não estava na lista, nem mude esses dois valores."
)


@dataclass(frozen=True)
class TituloPagar:
    fornecedor_codigo: str
    fornecedor_nome: str
    prefixo: str
    numero: str
    parcela: str
    natureza_codigo: str
    natureza_descricao: str
    valor_original: float
    data_emissao: date


@dataclass(frozen=True)
class CandidatoDuplicidade:
    fornecedor_codigo: str
    fornecedor_nome: str
    valor_original: float
    documentos: tuple[str, ...]
    data_emissao_min: date
    data_emissao_max: date


@dataclass(frozen=True)
class CandidatoAnomaliaValor:
    fornecedor_codigo: str
    fornecedor_nome: str
    natureza_descricao: str
    documento: str
    valor_original: float
    media_grupo: float
    data_emissao: date


@dataclass(frozen=True)
class AchadoDespesa:
    """`natureza_descricao`/`media_grupo` só existem pra `anomalia_valor` (o
    candidato de duplicidade não tem grupo/média — é uma comparação
    direta entre dois títulos). `data_emissao_min`/`data_emissao_max` são
    iguais em `anomalia_valor` (uma data só) e viram uma faixa de verdade
    só em `duplicidade`. Campos que já existiam calculados em
    `CandidatoDuplicidade`/`CandidatoAnomaliaValor` e eram jogados fora
    antes de chegar no front — a tela pedia clicar num achado pra ver o
    detalhamento (por que foi marcado, contra o que foi comparado), e essa
    conta já estava pronta, só faltava não descartar."""

    tipo: str
    fornecedor_codigo: str
    fornecedor_nome: str
    valor: float
    documentos: str
    descricao: str
    data_emissao_min: date
    data_emissao_max: date
    natureza_descricao: str | None = None
    media_grupo: float | None = None


def buscar_titulos_pagar(filiais: list[str], dias: int) -> list[TituloPagar]:
    """Títulos a pagar emitidos nos últimos `dias` dias, das filiais
    informadas — é isso (nunca a base inteira) que alimenta os dois
    algoritmos de candidato abaixo."""
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    sql = f"""
        SELECT fornecedor_codigo, fornecedor_nome, prefixo, numero, parcela,
               natureza_codigo, natureza_descricao, valor_original, data_emissao
        FROM vw_titulos_pagar
        WHERE filial IN {clausula_filial}
          AND data_emissao >= :desde
    """
    desde = date.today() - timedelta(days=dias)
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, desde=desde, **binds_filial)
        linhas = cursor.fetchall()

    return [
        TituloPagar(
            fornecedor_codigo=fornecedor_codigo,
            fornecedor_nome=fornecedor_nome,
            prefixo=prefixo,
            numero=numero,
            parcela=parcela,
            natureza_codigo=natureza_codigo,
            natureza_descricao=natureza_descricao,
            valor_original=float(_comum.serializar(valor_original)),
            data_emissao=data_emissao.date() if hasattr(data_emissao, "date") else data_emissao,
        )
        for (
            fornecedor_codigo,
            fornecedor_nome,
            prefixo,
            numero,
            parcela,
            natureza_codigo,
            natureza_descricao,
            valor_original,
            data_emissao,
        ) in linhas
    ]


async def analisar_despesas(
    ollama_client: AsyncClient, modelo: str, titulos: list[TituloPagar]
) -> list[AchadoDespesa]:
    candidatos_duplicidade = _candidatos_duplicidade(titulos)
    candidatos_anomalia = _candidatos_anomalia_valor(titulos)
    if not candidatos_duplicidade and not candidatos_anomalia:
        return []

    candidatos_por_chave: dict[tuple[str, float, str], CandidatoDuplicidade | CandidatoAnomaliaValor] = {
        (c.fornecedor_codigo, round(c.valor_original, 2), "duplicidade"): c for c in candidatos_duplicidade
    }
    candidatos_por_chave.update(
        {(c.fornecedor_codigo, round(c.valor_original, 2), "anomalia_valor"): c for c in candidatos_anomalia}
    )

    try:
        resposta = await ollama_client.chat(
            model=modelo,
            messages=[
                {"role": "system", "content": _PROMPT_SISTEMA},
                {
                    "role": "user",
                    "content": _candidatos_para_texto(candidatos_duplicidade, candidatos_anomalia),
                },
            ],
            format=_SCHEMA,
            options=OPCOES_OLLAMA_PADRAO,
        )
    except Exception:
        return _achados_sem_descricao_ia(candidatos_duplicidade, candidatos_anomalia)

    achados_brutos = resposta_json_como_dict(resposta.message.content).get("achados")
    if not isinstance(achados_brutos, list):
        return _achados_sem_descricao_ia(candidatos_duplicidade, candidatos_anomalia)

    achados = [
        achado
        for bruto in achados_brutos
        if (achado := _achado_fundamentado(bruto, candidatos_por_chave)) is not None
    ]
    return achados


# _achado_a_partir_de_candidato, _achado_fundamentado, _achados_sem_descricao_ia,
# _candidatos_anomalia_valor, _candidatos_duplicidade e _candidatos_para_texto
# só são usadas por analisar_despesas, logo depois dela, em ordem alfabética
# entre si.
def _achado_a_partir_de_candidato(
    tipo: str, candidato: CandidatoDuplicidade | CandidatoAnomaliaValor, descricao: str
) -> AchadoDespesa:
    if isinstance(candidato, CandidatoDuplicidade):
        return AchadoDespesa(
            tipo=tipo,
            fornecedor_codigo=candidato.fornecedor_codigo,
            fornecedor_nome=candidato.fornecedor_nome,
            valor=candidato.valor_original,
            documentos=", ".join(candidato.documentos),
            descricao=descricao,
            data_emissao_min=candidato.data_emissao_min,
            data_emissao_max=candidato.data_emissao_max,
        )
    return AchadoDespesa(
        tipo=tipo,
        fornecedor_codigo=candidato.fornecedor_codigo,
        fornecedor_nome=candidato.fornecedor_nome,
        valor=candidato.valor_original,
        documentos=candidato.documento,
        descricao=descricao,
        data_emissao_min=candidato.data_emissao,
        data_emissao_max=candidato.data_emissao,
        natureza_descricao=candidato.natureza_descricao,
        media_grupo=candidato.media_grupo,
    )


def _achado_fundamentado(
    bruto: object,
    candidatos_por_chave: dict[tuple[str, float, str], CandidatoDuplicidade | CandidatoAnomaliaValor],
) -> AchadoDespesa | None:
    if not isinstance(bruto, dict):
        return None

    fornecedor_codigo = bruto.get("fornecedor_codigo")
    valor_original = bruto.get("valor_original")
    tipo = bruto.get("tipo")
    descricao = bruto.get("descricao")
    if not isinstance(fornecedor_codigo, str) or not fornecedor_codigo:
        return None
    if isinstance(valor_original, bool) or not isinstance(valor_original, (int, float)):
        return None
    if not isinstance(tipo, str) or not isinstance(descricao, str) or not descricao.strip():
        return None

    candidato = candidatos_por_chave.get((fornecedor_codigo, round(float(valor_original), 2), tipo))
    if candidato is None:
        return None

    return _achado_a_partir_de_candidato(tipo, candidato, descricao.strip())


def _achados_sem_descricao_ia(
    candidatos_duplicidade: list[CandidatoDuplicidade], candidatos_anomalia: list[CandidatoAnomaliaValor]
) -> list[AchadoDespesa]:
    achados = [
        _achado_a_partir_de_candidato(
            "duplicidade",
            c,
            f"{len(c.documentos)} títulos do mesmo fornecedor com o mesmo valor, emitidos entre "
            f"{c.data_emissao_min.isoformat()} e {c.data_emissao_max.isoformat()}.",
        )
        for c in candidatos_duplicidade
    ]
    achados.extend(
        _achado_a_partir_de_candidato(
            "anomalia_valor",
            c,
            f"Valor muito acima da média da natureza '{c.natureza_descricao}' "
            f"(média do grupo: {c.media_grupo}).",
        )
        for c in candidatos_anomalia
    )
    return achados


def _candidatos_anomalia_valor(titulos: list[TituloPagar]) -> list[CandidatoAnomaliaValor]:
    grupos: dict[str, list[TituloPagar]] = {}
    for titulo in titulos:
        grupos.setdefault(titulo.natureza_codigo, []).append(titulo)

    candidatos = []
    for grupo in grupos.values():
        if len(grupo) < _TAMANHO_MINIMO_GRUPO_ANOMALIA:
            continue
        for titulo in grupo:
            # Média/desvio-padrão calculados SEM o próprio candidato — senão
            # um valor bem fora do padrão infla a própria média/desvio do
            # grupo e escapa da detecção (quanto mais extremo o outlier,
            # mais alto o limiar fica, na direção errada).
            outros_valores = [outro.valor_original for outro in grupo if outro is not titulo]
            media = statistics.mean(outros_valores)
            desvio_padrao = statistics.pstdev(outros_valores)
            if desvio_padrao == 0:
                continue
            limiar = media + _LIMIAR_DESVIOS_PADRAO * desvio_padrao
            if titulo.valor_original > limiar:
                candidatos.append(
                    CandidatoAnomaliaValor(
                        fornecedor_codigo=titulo.fornecedor_codigo,
                        fornecedor_nome=titulo.fornecedor_nome,
                        natureza_descricao=titulo.natureza_descricao,
                        documento=f"{titulo.prefixo}-{titulo.numero}-{titulo.parcela}",
                        valor_original=titulo.valor_original,
                        media_grupo=round(media, 2),
                        data_emissao=titulo.data_emissao,
                    )
                )
    return candidatos


def _candidatos_duplicidade(titulos: list[TituloPagar]) -> list[CandidatoDuplicidade]:
    grupos: dict[tuple[str, float], list[TituloPagar]] = {}
    for titulo in titulos:
        grupos.setdefault((titulo.fornecedor_codigo, titulo.valor_original), []).append(titulo)

    candidatos = []
    for (fornecedor_codigo, valor_original), grupo in grupos.items():
        documentos_distintos = {(titulo.prefixo, titulo.numero) for titulo in grupo}
        if len(documentos_distintos) < 2:
            continue
        datas = [titulo.data_emissao for titulo in grupo]
        if (max(datas) - min(datas)).days > _JANELA_DIAS_DUPLICIDADE:
            continue
        candidatos.append(
            CandidatoDuplicidade(
                fornecedor_codigo=fornecedor_codigo,
                fornecedor_nome=grupo[0].fornecedor_nome,
                valor_original=valor_original,
                documentos=tuple(f"{titulo.prefixo}-{titulo.numero}-{titulo.parcela}" for titulo in grupo),
                data_emissao_min=min(datas),
                data_emissao_max=max(datas),
            )
        )
    return candidatos


def _candidatos_para_texto(
    candidatos_duplicidade: list[CandidatoDuplicidade], candidatos_anomalia: list[CandidatoAnomaliaValor]
) -> str:
    blocos = []
    if candidatos_duplicidade:
        blocos.append("POSSÍVEIS DUPLICIDADES (mesmo fornecedor, mesmo valor, datas próximas):")
        blocos.extend(
            f"- fornecedor_codigo {c.fornecedor_codigo} ({c.fornecedor_nome}), valor {c.valor_original}, "
            f"documentos: {', '.join(c.documentos)}, emitidos entre {c.data_emissao_min} e {c.data_emissao_max}"
            for c in candidatos_duplicidade
        )
    if candidatos_anomalia:
        blocos.append("\nVALORES FORA DO PADRÃO (muito acima da média da natureza):")
        blocos.extend(
            f"- fornecedor_codigo {c.fornecedor_codigo} ({c.fornecedor_nome}), natureza "
            f"'{c.natureza_descricao}', valor {c.valor_original} (média do grupo: {c.media_grupo}, "
            f"documento {c.documento}, emitido em {c.data_emissao})"
            for c in candidatos_anomalia
        )
    return "\n".join(blocos)
