"""Geração do perfil estruturado de um candidato a partir do texto do
currículo (já extraído — ver `tools/rh/extracao_curriculo.py`) via IA
(Ollama). Mesmo padrão de chamada já usado no resto do projeto
(`agent/auditoria/analise.py`, `agent/financeiro/financeiro.py`): `format=`
JSON schema, nunca texto livre.

MAIS GRANULAR (2026-08) do que a primeira versão (que só pedia um parágrafo
livre de resumo): a extração agora separa habilidades técnicas, experiência
profissional, formação, senioridade etc. em campos próprios — o resumo
livre continua existindo (`resumo_objetivo`, usado pro embedding e pra
exibição rápida), mas o resto fica estruturado pra `busca_candidatos.py`
poder comparar dado específico (ex: "tem PostgreSQL?", "quantos anos de
experiência?") contra a descrição de uma vaga, em vez de inferir tudo de um
parágrafo solto — é a especificidade que o time de RH pediu.

Diferente do modelo bem anterior (score fixo contra 6 dimensões de "DNA
Agro" por vaga, removido antes desta rodada), aqui a IA só descreve
objetivamente quem é o candidato — a avaliação de fit com uma vaga
específica acontece depois, sob demanda, em `agent/rh/busca_candidatos.py`.

Validação (`_avaliacao_fundamentada`-style) é mais leve aqui que em outros
agentes do projeto: só `nome_candidato`/`resumo_objetivo` são exigidos de
verdade (são os dois campos que o resto do pipeline depende — nome pra
exibição, resumo pro embedding). Os campos estruturados são "nice to
have": se a IA devolver algo malformado num campo secundário, esse campo
cai num valor vazio/neutro em vez de descartar a análise inteira — perder
uma lista de certificações não deveria custar recomeçar o currículo do
zero."""

import json
from dataclasses import dataclass, field

from ollama import AsyncClient

from agente_oracle.agent.rh.embeddings import AnaliseIndisponivel

# Mesma constante usada em financeiro.py/analise.py — evita reservar mais
# RAM do que o prompt (texto do currículo) precisa.
_OPCOES_OLLAMA = {"num_ctx": 16384}

_NIVEIS_SENIORIDADE = ("estagiario", "junior", "pleno", "senior", "especialista", "nao_identificado")
_STATUS_FORMACAO = ("concluido", "cursando", "nao_identificado")

_SCHEMA_HABILIDADES = {
    "type": "object",
    "properties": {
        "linguagens": {"type": "array", "items": {"type": "string"}},
        "frameworks_bibliotecas": {"type": "array", "items": {"type": "string"}},
        "bancos_de_dados": {"type": "array", "items": {"type": "string"}},
        "ferramentas_plataformas": {"type": "array", "items": {"type": "string"}},
        "metodologias": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "linguagens",
        "frameworks_bibliotecas",
        "bancos_de_dados",
        "ferramentas_plataformas",
        "metodologias",
    ],
}

_SCHEMA_EXPERIENCIA = {
    "type": "object",
    "properties": {
        "empresa": {"type": "string"},
        "cargo": {"type": "string"},
        "data_inicio": {"type": "string"},
        "data_fim": {"type": "string"},
        "principais_responsabilidades": {"type": "array", "items": {"type": "string"}},
        "tecnologias_utilizadas": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "empresa",
        "cargo",
        "data_inicio",
        "data_fim",
        "principais_responsabilidades",
        "tecnologias_utilizadas",
    ],
}

_SCHEMA_FORMACAO = {
    "type": "object",
    "properties": {
        "curso": {"type": "string"},
        "instituicao": {"type": "string"},
        "status": {"type": "string", "enum": list(_STATUS_FORMACAO)},
    },
    "required": ["curso", "instituicao", "status"],
}

_SCHEMA = {
    "type": "object",
    "properties": {
        "nome_candidato": {"type": "string"},
        "resumo_objetivo": {"type": "string"},
        "nivel_senioridade": {"type": "string", "enum": list(_NIVEIS_SENIORIDADE)},
        "anos_experiencia_total": {"type": "number"},
        "area_atuacao_principal": {"type": "string"},
        "areas_atuacao_secundarias": {"type": "array", "items": {"type": "string"}},
        "habilidades_tecnicas": _SCHEMA_HABILIDADES,
        "experiencias_profissionais": {"type": "array", "items": _SCHEMA_EXPERIENCIA},
        "formacao_academica": {"type": "array", "items": _SCHEMA_FORMACAO},
        "certificacoes": {"type": "array", "items": {"type": "string"}},
        "idiomas": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "nome_candidato",
        "resumo_objetivo",
        "nivel_senioridade",
        "anos_experiencia_total",
        "area_atuacao_principal",
        "areas_atuacao_secundarias",
        "habilidades_tecnicas",
        "experiencias_profissionais",
        "formacao_academica",
        "certificacoes",
        "idiomas",
    ],
}

_PROMPT_SISTEMA = (
    "Você extrai dados estruturados de um currículo pra uso num sistema de busca de candidatos. "
    "Seja o mais específico e granular possível — a busca depois vai comparar esses dados "
    'diretamente contra a descrição de vagas, então termos exatos ("PostgreSQL", "SQL Server") '
    'são muito mais úteis que termos vagos ("experiência com bancos de dados").\n\n'
    "Regras:\n"
    "- Baseie-se exclusivamente no que está escrito no currículo. Nunca infira ou complete "
    "informação ausente.\n"
    "- Não avalie fit com nenhuma vaga específica — isso é feito depois, por outro agente.\n"
    "- Campo de lista sem informação no currículo: devolva lista vazia, nunca invente item.\n"
    "- Campo de texto sem informação no currículo (ex: data_inicio, data_fim, instituição): "
    'devolva string vazia "".\n'
    "- anos_experiencia_total: sua melhor estimativa numérica somando os períodos de experiência "
    "profissional relevante; 0 se não der pra estimar.\n"
    "- nivel_senioridade: escolha com base no tempo de experiência e na seniority dos cargos "
    'descritos, não invente — use "nao_identificado" se não der pra inferir com confiança.\n'
    "- Datas em formato AAAA-MM quando o currículo permitir essa precisão.\n"
    "- resumo_objetivo: um ou dois parágrafos curtos, em português, tom neutro e direto, pra "
    "leitura humana rápida — experiência relevante, principais habilidades, área de atuação e "
    "senioridade aparente.\n"
    "- Extraia também o nome completo do candidato — se não encontrar um nome claro, use "
    '"Candidato não identificado".'
)


# _lista_textos, _texto e _valor_no_conjunto são usadas tanto por
# gerar_perfil quanto pelos helpers privados dela (_experiencias_profissionais
# etc.) — bloco compartilhado, em ordem alfabética, antes da classe/pública.
def _lista_textos(valor: object) -> list[str]:
    if not isinstance(valor, list):
        return []
    return [item.strip() for item in valor if isinstance(item, str) and item.strip()]


def _texto(valor: object) -> str:
    return valor.strip() if isinstance(valor, str) else ""


def _valor_no_conjunto(valor: object, conjunto: tuple[str, ...]) -> str:
    return valor if valor in conjunto else "nao_identificado"


@dataclass(frozen=True)
class PerfilCandidato:
    nome_candidato: str
    resumo_objetivo: str
    nivel_senioridade: str
    anos_experiencia_total: float | None
    area_atuacao_principal: str
    areas_atuacao_secundarias: list[str] = field(default_factory=list)
    habilidades_tecnicas: dict = field(default_factory=dict)
    experiencias_profissionais: list[dict] = field(default_factory=list)
    formacao_academica: list[dict] = field(default_factory=list)
    certificacoes: list[str] = field(default_factory=list)
    idiomas: list[str] = field(default_factory=list)

    def campos_estruturados(self) -> dict:
        """Tudo exceto `nome_candidato`/`resumo_objetivo`, que têm coluna
        própria em `rh_candidatos` — o resto vai inteiro pra
        `perfil_estruturado` (JSONB)."""
        return {
            "nivel_senioridade": self.nivel_senioridade,
            "anos_experiencia_total": self.anos_experiencia_total,
            "area_atuacao_principal": self.area_atuacao_principal,
            "areas_atuacao_secundarias": self.areas_atuacao_secundarias,
            "habilidades_tecnicas": self.habilidades_tecnicas,
            "experiencias_profissionais": self.experiencias_profissionais,
            "formacao_academica": self.formacao_academica,
            "certificacoes": self.certificacoes,
            "idiomas": self.idiomas,
        }


async def gerar_perfil(ollama_client: AsyncClient, modelo: str, texto_curriculo: str) -> PerfilCandidato:
    try:
        resposta = await ollama_client.chat(
            model=modelo,
            messages=[
                {"role": "system", "content": _PROMPT_SISTEMA},
                {"role": "user", "content": f"CURRÍCULO:\n{texto_curriculo}"},
            ],
            format=_SCHEMA,
            options=_OPCOES_OLLAMA,
        )
        corpo = json.loads(resposta.message.content or "{}")
    except Exception as erro:
        raise AnaliseIndisponivel("Não foi possível analisar o currículo com a IA no momento.") from erro

    nome_candidato = _texto(corpo.get("nome_candidato"))
    resumo_objetivo = _texto(corpo.get("resumo_objetivo"))
    if not nome_candidato or not resumo_objetivo:
        raise AnaliseIndisponivel("A IA devolveu uma resposta em formato inesperado.")

    return PerfilCandidato(
        nome_candidato=nome_candidato,
        resumo_objetivo=resumo_objetivo,
        nivel_senioridade=_valor_no_conjunto(corpo.get("nivel_senioridade"), _NIVEIS_SENIORIDADE),
        anos_experiencia_total=_numero_positivo_ou_none(corpo.get("anos_experiencia_total")),
        area_atuacao_principal=_texto(corpo.get("area_atuacao_principal")) or "Não identificado",
        areas_atuacao_secundarias=_lista_textos(corpo.get("areas_atuacao_secundarias")),
        habilidades_tecnicas=_habilidades_tecnicas(corpo.get("habilidades_tecnicas")),
        experiencias_profissionais=_experiencias_profissionais(corpo.get("experiencias_profissionais")),
        formacao_academica=_formacao_academica(corpo.get("formacao_academica")),
        certificacoes=_lista_textos(corpo.get("certificacoes")),
        idiomas=_lista_textos(corpo.get("idiomas")),
    )


# _experiencias_profissionais, _formacao_academica, _habilidades_tecnicas e
# _numero_positivo_ou_none só são usadas por gerar_perfil, logo depois
# dela, em ordem alfabética entre si.
def _experiencias_profissionais(valor: object) -> list[dict]:
    if not isinstance(valor, list):
        return []
    experiencias = []
    for item in valor:
        if not isinstance(item, dict):
            continue
        empresa = _texto(item.get("empresa"))
        cargo = _texto(item.get("cargo"))
        if not empresa and not cargo:
            continue
        experiencias.append(
            {
                "empresa": empresa,
                "cargo": cargo,
                "data_inicio": _texto(item.get("data_inicio")) or None,
                "data_fim": _texto(item.get("data_fim")) or None,
                "principais_responsabilidades": _lista_textos(item.get("principais_responsabilidades")),
                "tecnologias_utilizadas": _lista_textos(item.get("tecnologias_utilizadas")),
            }
        )
    return experiencias


def _formacao_academica(valor: object) -> list[dict]:
    if not isinstance(valor, list):
        return []
    formacoes = []
    for item in valor:
        if not isinstance(item, dict):
            continue
        curso = _texto(item.get("curso"))
        if not curso:
            continue
        formacoes.append(
            {
                "curso": curso,
                "instituicao": _texto(item.get("instituicao")),
                "status": _valor_no_conjunto(item.get("status"), _STATUS_FORMACAO),
            }
        )
    return formacoes


def _habilidades_tecnicas(valor: object) -> dict:
    dados = valor if isinstance(valor, dict) else {}
    chaves = (
        "linguagens",
        "frameworks_bibliotecas",
        "bancos_de_dados",
        "ferramentas_plataformas",
        "metodologias",
    )
    return {chave: _lista_textos(dados.get(chave)) for chave in chaves}


def _numero_positivo_ou_none(valor: object) -> float | None:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor <= 0:
        return None
    return float(valor)
