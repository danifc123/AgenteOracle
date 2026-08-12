import json

import pytest

from agente_oracle.agent.rh import perfil_candidato as mod
from agente_oracle.agent.rh.embeddings import AnaliseIndisponivel


class _RespostaFake:
    def __init__(self, conteudo: str | None):
        self.message = type("Mensagem", (), {"content": conteudo})()


class _OllamaClientFake:
    """`gerar_perfil` só usa `chat(...)` — um fake simples já satisfaz essa
    interface, sem precisar de um servidor Ollama de verdade."""

    def __init__(self, conteudo: str | None = None, levantar: Exception | None = None):
        self._conteudo = conteudo
        self._levantar = levantar

    async def chat(self, **_kwargs):
        if self._levantar:
            raise self._levantar
        return _RespostaFake(self._conteudo)


def _perfil_bruto(**overrides) -> dict:
    base = {
        "nome_candidato": "Maria Silva",
        "resumo_objetivo": "Resumo qualquer.",
        "nivel_senioridade": "pleno",
        "anos_experiencia_total": 4,
        "area_atuacao_principal": "Desenvolvimento de Software",
        "areas_atuacao_secundarias": ["Dados"],
        "habilidades_tecnicas": {
            "linguagens": ["Python"],
            "frameworks_bibliotecas": ["Django"],
            "bancos_de_dados": ["PostgreSQL"],
            "ferramentas_plataformas": ["Docker"],
            "metodologias": ["Scrum"],
        },
        "experiencias_profissionais": [
            {
                "empresa": "Empresa X",
                "cargo": "Dev Backend",
                "data_inicio": "2021-01",
                "data_fim": "2023-06",
                "principais_responsabilidades": ["Manutenção de API"],
                "tecnologias_utilizadas": ["Python", "PostgreSQL"],
            }
        ],
        "formacao_academica": [
            {"curso": "Ciência da Computação", "instituicao": "UFMT", "status": "concluido"}
        ],
        "certificacoes": ["AWS Certified Developer"],
        "idiomas": ["Português", "Inglês"],
    }
    base.update(overrides)
    return base


def _perfil_json(**overrides) -> str:
    return json.dumps(_perfil_bruto(**overrides))


class TestGerarPerfil:
    async def test_resposta_valida_devolve_perfil_completo(self):
        cliente = _OllamaClientFake(conteudo=_perfil_json())
        perfil = await mod.gerar_perfil(cliente, "modelo-teste", "texto do currículo")

        assert perfil.nome_candidato == "Maria Silva"
        assert perfil.resumo_objetivo == "Resumo qualquer."
        assert perfil.nivel_senioridade == "pleno"
        assert perfil.anos_experiencia_total == 4.0
        assert perfil.area_atuacao_principal == "Desenvolvimento de Software"
        assert perfil.habilidades_tecnicas["linguagens"] == ["Python"]
        assert perfil.experiencias_profissionais[0]["empresa"] == "Empresa X"
        assert perfil.formacao_academica[0]["status"] == "concluido"
        assert perfil.certificacoes == ["AWS Certified Developer"]

    async def test_nivel_senioridade_fora_do_conjunto_vira_nao_identificado(self):
        cliente = _OllamaClientFake(conteudo=_perfil_json(nivel_senioridade="lendário"))
        perfil = await mod.gerar_perfil(cliente, "modelo-teste", "texto")
        assert perfil.nivel_senioridade == "nao_identificado"

    async def test_anos_experiencia_zero_ou_negativo_vira_none(self):
        cliente = _OllamaClientFake(conteudo=_perfil_json(anos_experiencia_total=0))
        perfil = await mod.gerar_perfil(cliente, "modelo-teste", "texto")
        assert perfil.anos_experiencia_total is None

    async def test_experiencia_sem_empresa_nem_cargo_e_descartada(self):
        conteudo = _perfil_json(
            experiencias_profissionais=[
                {
                    "empresa": "",
                    "cargo": "",
                    "data_inicio": "",
                    "data_fim": "",
                    "principais_responsabilidades": [],
                    "tecnologias_utilizadas": [],
                }
            ]
        )
        cliente = _OllamaClientFake(conteudo=conteudo)
        perfil = await mod.gerar_perfil(cliente, "modelo-teste", "texto")
        assert perfil.experiencias_profissionais == []

    async def test_habilidades_malformadas_viram_listas_vazias(self):
        cliente = _OllamaClientFake(conteudo=_perfil_json(habilidades_tecnicas="não é um dict"))
        perfil = await mod.gerar_perfil(cliente, "modelo-teste", "texto")
        assert perfil.habilidades_tecnicas == {
            "linguagens": [],
            "frameworks_bibliotecas": [],
            "bancos_de_dados": [],
            "ferramentas_plataformas": [],
            "metodologias": [],
        }

    async def test_nome_ausente_levanta_indisponivel(self):
        bruto = _perfil_bruto()
        del bruto["nome_candidato"]
        cliente = _OllamaClientFake(conteudo=json.dumps(bruto))
        with pytest.raises(AnaliseIndisponivel):
            await mod.gerar_perfil(cliente, "modelo-teste", "texto")

    async def test_resumo_vazio_levanta_indisponivel(self):
        cliente = _OllamaClientFake(conteudo=_perfil_json(resumo_objetivo="   "))
        with pytest.raises(AnaliseIndisponivel):
            await mod.gerar_perfil(cliente, "modelo-teste", "texto")

    async def test_json_invalido_levanta_indisponivel(self):
        cliente = _OllamaClientFake(conteudo="isso não é json")
        with pytest.raises(AnaliseIndisponivel):
            await mod.gerar_perfil(cliente, "modelo-teste", "texto")

    async def test_falha_do_ollama_levanta_indisponivel(self):
        cliente = _OllamaClientFake(levantar=ConnectionError("Ollama fora do ar"))
        with pytest.raises(AnaliseIndisponivel):
            await mod.gerar_perfil(cliente, "modelo-teste", "texto")


class TestCamposEstruturados:
    def test_nao_inclui_nome_nem_resumo(self):
        perfil = mod.PerfilCandidato(
            nome_candidato="Maria",
            resumo_objetivo="Resumo",
            nivel_senioridade="pleno",
            anos_experiencia_total=None,
            area_atuacao_principal="TI",
        )
        campos = perfil.campos_estruturados()
        assert "nome_candidato" not in campos
        assert "resumo_objetivo" not in campos
        assert campos["nivel_senioridade"] == "pleno"
