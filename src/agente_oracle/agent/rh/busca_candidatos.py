"""Busca de candidatos por IA (RAG) — dado uma descrição de vaga em texto
livre, encontra os candidatos mais adequados entre os já analisados
(`agent/rh/perfil_candidato.py`).

Duas etapas: (1) **retrieval** — embedding da descrição contra o embedding
já salvo de cada candidato (`agent/rh/embeddings.py`), pega os N mais
próximos por similaridade de cosseno, tudo em Python (sem `pgvector`, ver
docstring de `embeddings.py`); (2) **generation** — manda só esse shortlist
pra IA, que rankeia e justifica cada um contra a descrição da vaga. Mesma
rede de segurança de sempre: `candidato_id` que a IA cita precisa estar no
shortlist que foi realmente enviado, nunca aceita um id inventado."""

import json
from dataclasses import dataclass

from ollama import AsyncClient

from agente_oracle.agent.rh.embeddings import AnaliseIndisponivel, gerar_embedding, similaridade_cosseno

# Mesma constante usada em financeiro.py/analise.py — evita reservar mais
# RAM do que o prompt (descrição da vaga + shortlist de candidatos) precisa.
_OPCOES_OLLAMA = {"num_ctx": 16384}

# Quantos candidatos (dos mais similares por embedding) vão pro shortlist
# que a IA efetivamente lê e rankeia — retrieval antes de generation, não
# manda o pool inteiro pra IA.
_TOP_N_SHORTLIST = 8

_SCHEMA = {
    "type": "object",
    "properties": {
        "resultados": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidato_id": {"type": "integer"},
                    "posicao": {"type": "integer"},
                    "justificativa": {"type": "string"},
                },
                "required": ["candidato_id", "posicao", "justificativa"],
            },
        }
    },
    "required": ["resultados"],
}

_PROMPT_SISTEMA = (
    "Você ajuda o time de RH a escolher o candidato mais adequado pra uma vaga, a partir de uma "
    "lista de candidatos pré-selecionados (já filtrados por similaridade — sua função é usar "
    "julgamento pra rankear e justificar, não pra descartar a lista inteira). Você recebe a "
    "descrição da necessidade da vaga e o perfil resumido de cada candidato (com um id numérico "
    "cada). Devolva um ranking usando `candidato_id` exatamente como foi enviado — posição 1 é o "
    "candidato mais adequado — com uma justificativa curta e específica pra cada um, citando o "
    "que no perfil dele conecta (ou não conecta bem) com a descrição da vaga. Pode incluir menos "
    "candidatos do que recebeu se algum for claramente inadequado, mas nunca invente um "
    "candidato que não estava na lista."
)


@dataclass(frozen=True)
class ResultadoBusca:
    candidato_id: int
    nome: str
    resumo_perfil: str
    nivel_senioridade: str
    area_atuacao_principal: str
    posicao: int
    justificativa: str
    similaridade: float


async def buscar_candidatos(
    ollama_client: AsyncClient,
    modelo: str,
    modelo_embedding: str,
    descricao_vaga: str,
    candidatos: list[dict],
) -> list[ResultadoBusca]:
    if not candidatos:
        raise AnaliseIndisponivel("Não há candidatos ativos cadastrados pra buscar.")

    embedding_busca = await gerar_embedding(ollama_client, modelo_embedding, descricao_vaga)

    candidatos_ordenados = sorted(
        (
            (candidato, similaridade_cosseno(embedding_busca, candidato["embedding"]))
            for candidato in candidatos
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    shortlist = candidatos_ordenados[:_TOP_N_SHORTLIST]
    candidatos_por_id = {candidato["id"]: candidato for candidato, _ in shortlist}
    similaridade_por_id = {candidato["id"]: similaridade for candidato, similaridade in shortlist}

    try:
        resposta = await ollama_client.chat(
            model=modelo,
            messages=[
                {"role": "system", "content": _PROMPT_SISTEMA},
                {"role": "user", "content": _prompt_usuario(descricao_vaga, [c for c, _ in shortlist])},
            ],
            format=_SCHEMA,
            options=_OPCOES_OLLAMA,
        )
        corpo = json.loads(resposta.message.content or "{}")
    except Exception as erro:
        raise AnaliseIndisponivel("Não foi possível buscar candidatos com a IA no momento.") from erro

    resultados_brutos = corpo.get("resultados")
    if not isinstance(resultados_brutos, list):
        raise AnaliseIndisponivel("A IA devolveu uma resposta em formato inesperado.")

    resultados = [
        resultado
        for bruto in resultados_brutos
        if (resultado := _resultado_fundamentado(bruto, candidatos_por_id, similaridade_por_id)) is not None
    ]
    if not resultados:
        raise AnaliseIndisponivel("A IA não devolveu nenhum resultado válido para essa busca.")

    return sorted(resultados, key=lambda item: item.posicao)


def _prompt_usuario(descricao_vaga: str, candidatos: list[dict]) -> str:
    candidatos_texto = "\n\n".join(_candidato_para_texto(candidato) for candidato in candidatos)
    return f"DESCRIÇÃO DA VAGA:\n{descricao_vaga}\n\nCANDIDATOS PRÉ-SELECIONADOS:\n{candidatos_texto}"


# _candidato_para_texto só é usada por _prompt_usuario, logo depois dela.
def _candidato_para_texto(candidato: dict) -> str:
    """Formata um candidato (com o `perfil_estruturado` que
    `tools/rh/candidatos.py::listar_para_busca` já devolve) em texto
    legível pro prompt — os campos granulares (senioridade, habilidades,
    experiências) é o que dá pra IA final comparar dado específico contra a
    descrição da vaga, em vez de só o resumo livre."""
    estruturado = candidato.get("perfil_estruturado") or {}
    linhas = [f"- id {candidato['id']}: {candidato['nome']}", f"  Resumo: {candidato['resumo_perfil']}"]

    senioridade = estruturado.get("nivel_senioridade")
    area = estruturado.get("area_atuacao_principal")
    anos = estruturado.get("anos_experiencia_total")
    if senioridade or area or anos:
        linhas.append(
            f"  Senioridade: {senioridade or 'não identificado'} | "
            f"Área principal: {area or 'não identificado'} | "
            f"Anos de experiência: {anos if anos is not None else 'não identificado'}"
        )

    habilidades = estruturado.get("habilidades_tecnicas") or {}
    partes_habilidades = [
        f"{rotulo}: {', '.join(valores)}"
        for rotulo, chave in (
            ("Linguagens", "linguagens"),
            ("Frameworks/bibliotecas", "frameworks_bibliotecas"),
            ("Bancos de dados", "bancos_de_dados"),
            ("Ferramentas/plataformas", "ferramentas_plataformas"),
        )
        if (valores := habilidades.get(chave))
    ]
    if partes_habilidades:
        linhas.append("  " + " | ".join(partes_habilidades))

    for experiencia in (estruturado.get("experiencias_profissionais") or [])[:4]:
        periodo = f"{experiencia.get('data_inicio') or '?'} a {experiencia.get('data_fim') or 'atual'}"
        linhas.append(
            f"  Experiência: {experiencia.get('cargo') or '?'} na {experiencia.get('empresa') or '?'} ({periodo})"
        )

    return "\n".join(linhas)


def _resultado_fundamentado(
    bruto: object, candidatos_por_id: dict[int, dict], similaridade_por_id: dict[int, float]
) -> ResultadoBusca | None:
    if not isinstance(bruto, dict):
        return None

    candidato_id = bruto.get("candidato_id")
    if not isinstance(candidato_id, int) or candidato_id not in candidatos_por_id:
        return None

    posicao = bruto.get("posicao")
    if not isinstance(posicao, int):
        return None

    justificativa = bruto.get("justificativa")
    if not isinstance(justificativa, str) or not justificativa.strip():
        return None

    candidato = candidatos_por_id[candidato_id]
    estruturado = candidato.get("perfil_estruturado") or {}
    return ResultadoBusca(
        candidato_id=candidato_id,
        nome=candidato["nome"],
        resumo_perfil=candidato["resumo_perfil"],
        nivel_senioridade=estruturado.get("nivel_senioridade") or "nao_identificado",
        area_atuacao_principal=estruturado.get("area_atuacao_principal") or "Não identificado",
        posicao=posicao,
        justificativa=justificativa.strip(),
        similaridade=similaridade_por_id[candidato_id],
    )
