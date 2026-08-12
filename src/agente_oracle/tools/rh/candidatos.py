"""Candidatos analisados pela IA (mock) contra as vagas críticas — tabela
própria no Postgres, mesmo padrão de `tools/rh/vagas.py`/
`tools/financeiro/layouts.py` (`CREATE TABLE IF NOT EXISTS`, sem migração
separada).

MOCK (2026-08): a "análise da IA" (pontuação, critérios, texto) é toda
gerada aqui por sorteio pseudo-aleatório — os critérios reais do "DNA Agro"
ainda dependem de um levantamento de requisitos com o time de RH (ver
`DIMENSOES_DNA_AGRO`, abaixo). Quando esse levantamento acontecer, só
`_gerar_resultado_vaga` precisa trocar por uma chamada de IA de verdade —
o resto (persistência condicionada ao limite, "vaga sugerida", status do
candidato) já fica pronto.

`criar_candidato` analisa o currículo contra TODAS as vagas ativas (não só
a escolhida no upload) — cada vaga recebe seu próprio score independente,
e a "vaga sugerida" é a de maior score. A decisão de salvar no Postgres usa
o MAIOR score entre todas as vagas (não só o da vaga escolhida): um
candidato bom que aplicou pra vaga errada não se perde, e é exatamente pra
isso que a vaga sugerida existe — a tela mostra as duas informações lado a
lado (score da vaga escolhida + vaga sugerida), então nunca fica ambíguo
por que um candidato com score baixo pra vaga X apareceu na lista.
"""

import json
import random
from datetime import UTC, datetime

from agente_oracle.db.connection import get_postgres_connection
from agente_oracle.tools.rh import vagas as vagas_tools

LIMITE_COMPATIBILIDADE_MINIMA = 70  # placeholder — RH ainda vai definir o valor real

DIMENSOES_DNA_AGRO: tuple[str, ...] = (
    "Vivência e afinidade com rotina de campo",
    "Adaptabilidade a sazonalidade e clima",
    "Mobilidade geográfica",
    "Resiliência e tolerância à pressão",
    "Alinhamento a valores do agronegócio",
    "Experiência técnica no setor",
)

_POOL_NOMES_MOCK: tuple[str, ...] = (
    "Gustavo Ribeiro Camargo",
    "Larissa Nascimento Vieira",
    "Eduardo Martins Sales",
    "Camila Ferreira Lopes",
    "Vinícius Oliveira Peixoto",
    "Beatriz Almeida Sant'Anna",
    "Rodrigo Souza Marchetti",
    "Fernanda Castro Guimarães",
)

_TEMPLATES_RESUMO_IA = {
    "alto": [
        lambda nome: (
            f"{nome} demonstra forte vivência prática em rotina de campo e boa aderência aos valores "
            "do agronegócio, com histórico consistente na área."
        ),
        lambda nome: (
            f"A trajetória de {nome} indica forte identificação com o setor, mobilidade compatível com "
            "a vaga e boa resiliência a rotinas sazonais."
        ),
    ],
    "medio": [
        lambda nome: (
            f"{nome} tem experiência relevante, mas o currículo não deixa claro o nível de vivência "
            "recente em rotina de campo — fit plausível, com pontos a confirmar em entrevista."
        ),
        lambda nome: (
            f"Boa base técnica identificada no currículo de {nome}, porém com sinais mistos de "
            "afinidade direta com o dia a dia do agronegócio."
        ),
    ],
    "baixo": [
        lambda nome: (
            f"O currículo de {nome} não apresenta indícios claros de vivência ou afinidade com o agronegócio."
        ),
        lambda nome: (
            f"{nome} tem um perfil predominantemente fora do setor agro, com baixa aderência aos "
            "critérios avaliados."
        ),
    ],
}

_COLUNAS = (
    "id, nome, vaga_id, vaga_sugerida_id, score, scores_por_vaga, resumo_ia, "
    "criterios, pontos_fortes, pontos_atencao, status, criado_em"
)

_tabela_garantida = False


# _garantir_tabela e _linha_para_candidato são usadas por mais de uma função
# pública (atualizar_status, criar_candidato, listar) — bloco compartilhado,
# em ordem alfabética, antes das públicas que dependem delas.
def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rh_candidatos (
            id BIGSERIAL PRIMARY KEY,
            nome VARCHAR NOT NULL,
            vaga_id BIGINT NOT NULL REFERENCES rh_vagas(id),
            vaga_sugerida_id BIGINT NOT NULL REFERENCES rh_vagas(id),
            score INTEGER NOT NULL,
            scores_por_vaga JSONB NOT NULL,
            resumo_ia TEXT NOT NULL,
            criterios JSONB NOT NULL,
            pontos_fortes JSONB NOT NULL,
            pontos_atencao JSONB NOT NULL,
            status VARCHAR NOT NULL DEFAULT 'pendente',
            criado_em TIMESTAMPTZ NOT NULL
        )
    """)
    _tabela_garantida = True


def _linha_para_candidato(linha: tuple) -> dict:
    (
        id_,
        nome,
        vaga_id,
        vaga_sugerida_id,
        score,
        scores_por_vaga,
        resumo_ia,
        criterios,
        pontos_fortes,
        pontos_atencao,
        status,
        criado_em,
    ) = linha
    return {
        "id": id_,
        "nome": nome,
        "vaga_id": vaga_id,
        "vaga_sugerida_id": vaga_sugerida_id,
        "score": score,
        "scores_por_vaga": _carregar_json(scores_por_vaga),
        "resumo_ia": resumo_ia,
        "criterios": _carregar_json(criterios),
        "pontos_fortes": _carregar_json(pontos_fortes),
        "pontos_atencao": _carregar_json(pontos_atencao),
        "status": status,
        "criado_em": criado_em,
        "salvo": True,
    }


# _carregar_json só é usada por _linha_para_candidato, logo depois dela.
def _carregar_json(valor):
    return json.loads(valor) if isinstance(valor, str) else valor


class SemVagaAtiva(Exception):
    """Levantada quando não há nenhuma vaga ativa cadastrada pra analisar o currículo contra ela."""


def atualizar_status(id_candidato: int, status: str) -> dict | None:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            f"UPDATE rh_candidatos SET status = :status WHERE id = :id RETURNING {_COLUNAS}",
            id=id_candidato,
            status=status,
        )
        linha = cursor.fetchone()
    return _linha_para_candidato(linha) if linha else None


def criar_candidato(vaga_id: int, nome_arquivo: str) -> dict:
    vagas_ativas = vagas_tools.listar(somente_ativas=True)
    if not vagas_ativas:
        raise SemVagaAtiva("Não há vagas ativas cadastradas pra analisar o currículo.")

    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("SELECT nome FROM rh_candidatos")
        nomes_usados = {linha[0] for linha in cursor.fetchall()}

    nome = _gerar_nome(nomes_usados)
    resultados_por_vaga = {vaga["id"]: _gerar_resultado_vaga(nome) for vaga in vagas_ativas}
    vaga_sugerida_id = max(resultados_por_vaga, key=lambda id_vaga: resultados_por_vaga[id_vaga]["score"])
    melhor_score = resultados_por_vaga[vaga_sugerida_id]["score"]
    resultado_vaga_escolhida = resultados_por_vaga.get(vaga_id, resultados_por_vaga[vaga_sugerida_id])
    scores_por_vaga = {str(id_vaga): resultado["score"] for id_vaga, resultado in resultados_por_vaga.items()}

    if melhor_score < LIMITE_COMPATIBILIDADE_MINIMA:
        return {
            "id": None,
            "nome": nome,
            "vaga_id": vaga_id,
            "vaga_sugerida_id": vaga_sugerida_id,
            "score": resultado_vaga_escolhida["score"],
            "melhor_score": melhor_score,
            "scores_por_vaga": scores_por_vaga,
            "resumo_ia": resultado_vaga_escolhida["resumo_ia"],
            "criterios": resultado_vaga_escolhida["criterios"],
            "pontos_fortes": resultado_vaga_escolhida["pontos_fortes"],
            "pontos_atencao": resultado_vaga_escolhida["pontos_atencao"],
            "status": "pendente",
            "criado_em": datetime.now(UTC),
            "salvo": False,
        }

    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            f"""
            INSERT INTO rh_candidatos
                (nome, vaga_id, vaga_sugerida_id, score, scores_por_vaga, resumo_ia, criterios,
                 pontos_fortes, pontos_atencao, status, criado_em)
            VALUES
                (:nome, :vaga_id, :vaga_sugerida_id, :score, :scores_por_vaga::jsonb, :resumo_ia,
                 :criterios::jsonb, :pontos_fortes::jsonb, :pontos_atencao::jsonb, 'pendente', :agora)
            RETURNING {_COLUNAS}
            """,
            nome=nome,
            vaga_id=vaga_id,
            vaga_sugerida_id=vaga_sugerida_id,
            score=resultado_vaga_escolhida["score"],
            scores_por_vaga=json.dumps(scores_por_vaga),
            resumo_ia=resultado_vaga_escolhida["resumo_ia"],
            criterios=json.dumps(resultado_vaga_escolhida["criterios"]),
            pontos_fortes=json.dumps(resultado_vaga_escolhida["pontos_fortes"]),
            pontos_atencao=json.dumps(resultado_vaga_escolhida["pontos_atencao"]),
            agora=datetime.now(UTC),
        )
        linha = cursor.fetchone()

    candidato = _linha_para_candidato(linha)
    candidato["melhor_score"] = melhor_score
    return candidato


# _gerar_nome e _gerar_resultado_vaga só são usadas por criar_candidato,
# logo depois dela.
def _gerar_nome(nomes_usados: set[str]) -> str:
    disponiveis = [nome for nome in _POOL_NOMES_MOCK if nome not in nomes_usados]
    if disponiveis:
        return random.choice(disponiveis)
    return f"Candidato {len(nomes_usados) + 1}"


def _gerar_resultado_vaga(nome: str) -> dict:
    score = round(35 + random.random() * 60)
    nivel = nivel_fit(score)
    criterios = [
        {"nome": dimensao, "nota": max(15, min(99, round(score + (random.random() * 20 - 10))))}
        for dimensao in DIMENSOES_DNA_AGRO
    ]
    return {
        "score": score,
        "criterios": criterios,
        "resumo_ia": random.choice(_TEMPLATES_RESUMO_IA[nivel])(nome),
        "pontos_fortes": []
        if nivel == "baixo"
        else ["Perfil extraído pela IA com aderência aos critérios avaliados da vaga"],
        "pontos_atencao": (
            []
            if nivel == "alto"
            else ["Análise gerada automaticamente pela IA — vale confirmar os pontos abaixo em entrevista"]
        ),
    }


def listar(vaga_id: int) -> list[dict]:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            f"SELECT {_COLUNAS} FROM rh_candidatos WHERE vaga_id = :vaga_id ORDER BY score DESC",
            vaga_id=vaga_id,
        )
        linhas = cursor.fetchall()
    return [_linha_para_candidato(linha) for linha in linhas]


def nivel_fit(score: int) -> str:
    if score >= 75:
        return "alto"
    if score >= 50:
        return "medio"
    return "baixo"
