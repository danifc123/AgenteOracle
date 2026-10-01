"""Cadastro de LLM feito pelo usuário — substitui os dois provedores fixos
no código (`Ollama`/`OCI`, ver histórico de `config.py`) por uma tabela que
qualquer desenvolvedor pode editar pela tela `/ti/provedores`, sem precisar
de deploy novo pra ligar um provedor a mais.

Cada linha é UMA conexão + UM modelo (não "um vendor com vários modelos")
— de propósito: o suporte Oracle confirmou que modelos diferentes da OCI
exigem APIs diferentes (`estilo_api`), então cadastrar cada combinação
como sua própria linha deixa isso explícito em vez de escondido num `if`
de código, e permite ativar/trocar entre modelos do mesmo vendor sem
reeditar nada, só trocando qual linha está ativa.

`tipo_conexao` é fechado de propósito — são os protocolos que o projeto
sabe falar (`ollama.AsyncClient` nativo, `ClienteOpenAICompativel`, e
`ClienteOciNativo` pro SDK nativo da OCI — assinatura RSA, usado pelos
modelos que não têm endpoint compatível com OpenAI, ex: embedding). Um
protocolo genuinamente novo ainda exige código novo (um cliente que saiba
falar esse protocolo) — o que ESTE cadastro generaliza é só o formato das
CREDENCIAIS: `base_url`/`api_key`/`projeto_id` cobrem os dois primeiros
tipos; `credenciais_extra` (JSONB livre) cobre qualquer formato de
credencial que um tipo novo precise, sem exigir `ALTER TABLE` de novo
(ver `credenciais_extra` abaixo).

`capacidades` (`"chat"`/`"embedding"`, pode ter as duas) diz o que aquele
modelo sabe fazer — importa porque só 1 provedor pode estar "ativo" por
vez no sistema hoje (`configuracoes_provedor.provedor_llm_ativo_id`):
`server/ti/provedores_llm.py::_ativar` recusa ativar um provedor sem
capacidade "chat", pra não deixar TI/RH inteiro sem conseguir conversar
por engano.

Preço é opcional (`0` = sem custo, é o padrão) — inclusive pra Ollama,
que não tem custo real em dinheiro: o campo existe igual pra todo mundo,
quem cadastra decide se preenche. A conversão de tokens pra custo usa
sempre o preço CADASTRADO HOJE, não um preço congelado no momento de cada
chamada — mais simples, e como não convertemos moeda (cada linha só tem
um prefixo de exibição, `moeda`), o custo é sempre mostrado por linha,
nunca somado entre provedores com moedas diferentes.

`credencial_atualizada_em` é SÓ um aviso (pedido do Daniel, 2026-09-25) —
não expira/bloqueia nada sozinho, só marca a última vez que `api_key` ou
`credenciais_extra` foram REALMENTE trocados por um valor novo (não toda
edição — editar só o preço, por exemplo, não conta). Começa igual a
`criado_em` (a credencial inicial "acabou de ser configurada" também).
`server/ti/provedores_llm.py` expõe isso pro front decidir quando mostrar
o aviso de "considere renovar"."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from agente_oracle.db.connection import DatabaseError, eh_erro_valor_duplicado, get_postgres_connection

TipoConexao = Literal["ollama", "openai_compativel", "oci_nativo"]
EstiloApi = Literal["chat_completions", "responses"]
Capacidade = Literal["chat", "embedding"]

_TIPOS_CONEXAO_VALIDOS: tuple[TipoConexao, ...] = ("ollama", "openai_compativel", "oci_nativo")
_ESTILOS_API_VALIDOS: tuple[EstiloApi, ...] = ("chat_completions", "responses")
_CAPACIDADES_VALIDAS: tuple[Capacidade, ...] = ("chat", "embedding")

# Modelo -> `estilo_api` CONHECIDO pros modelos de chat da OCI já liberados
# (confirmado com o suporte Oracle — ver docstring de
# `tools/ia/cliente_openai_compativel.py`): não é escolha livre de quem
# cadastra, é o próprio modelo que exige uma API ou outra. `criar`/
# `atualizar` corrigem sozinhos o `estilo_api` quando o modelo bate com um
# destes — sem isso, escolher o estilo errado só dava erro na hora de
# TESTAR a conexão, com uma mensagem crua da API (`Entity with key X not
# found`) que não dizia o que fazer (achado do usuário, 2026-10-01: ele
# reabriu "Editar" com a tela desatualizada e resalvou o valor errado por
# cima da correção manual, o que só reforça que isso não pode depender de
# ninguém lembrar de escolher certo). Modelo novo liberado no futuro:
# adiciona aqui, não precisa mexer em mais nada.
_ESTILO_API_CONHECIDO: dict[str, EstiloApi] = {
    "openai.gpt-oss-120b": "responses",
    "meta.llama-3.3-70b-instruct": "chat_completions",
    "meta.llama-4-scout-17b-16e-instruct": "chat_completions",
}

# Campos guardados como JSONB — únicos que passam por `json.dumps`/`::jsonb`
# na escrita, tanto em `criar` quanto em `atualizar`.
_CAMPOS_JSON = ("capacidades", "credenciais_extra")

_tabela_garantida = False

# Campos que, quando vêm preenchidos num `atualizar`, significam "a
# credencial foi trocada de verdade" — bump em `credencial_atualizada_em`
# (ver `_deve_renovar_credencial`).
_CAMPOS_CREDENCIAL = ("api_key", "credenciais_extra")

_COLUNAS = (
    "id, nome, tipo_conexao, base_url, api_key, projeto_id, modelo, estilo_api, "
    "preco_entrada_por_1k, preco_saida_por_1k, moeda, capacidades, credenciais_extra, "
    "credencial_atualizada_em, criado_em"
)


class ProvedorLlmJaExiste(Exception):
    """Levantada quando `nome` já está cadastrado — mensagem amigável em
    vez do erro cru de violação de unicidade do Postgres subindo."""


@dataclass(frozen=True)
class ProvedorLLM:
    id: int
    nome: str
    tipo_conexao: TipoConexao
    base_url: str
    api_key: str
    projeto_id: str
    modelo: str
    estilo_api: EstiloApi
    preco_entrada_por_1k: Decimal
    preco_saida_por_1k: Decimal
    moeda: str
    capacidades: list[Capacidade]
    credenciais_extra: dict | None
    credencial_atualizada_em: datetime
    criado_em: datetime


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS provedores_llm (
            id BIGSERIAL PRIMARY KEY,
            nome VARCHAR NOT NULL UNIQUE,
            tipo_conexao VARCHAR NOT NULL,
            base_url VARCHAR NOT NULL,
            api_key VARCHAR,
            projeto_id VARCHAR,
            modelo VARCHAR NOT NULL,
            estilo_api VARCHAR NOT NULL DEFAULT 'chat_completions',
            preco_entrada_por_1k NUMERIC NOT NULL DEFAULT 0,
            preco_saida_por_1k NUMERIC NOT NULL DEFAULT 0,
            moeda VARCHAR NOT NULL DEFAULT 'R$',
            criado_em TIMESTAMPTZ NOT NULL
        )
    """)
    # Aditivas de propósito (ver docstring do módulo) — o `DEFAULT` do
    # Postgres já preenche `capacidades` das linhas já cadastradas como
    # `["chat"]` sozinho, sem precisar de UPDATE manual.
    cursor.execute(
        "ALTER TABLE provedores_llm ADD COLUMN IF NOT EXISTS capacidades JSONB NOT NULL DEFAULT '[\"chat\"]'"
    )
    cursor.execute("ALTER TABLE provedores_llm ADD COLUMN IF NOT EXISTS credenciais_extra JSONB")
    cursor.execute("ALTER TABLE provedores_llm ADD COLUMN IF NOT EXISTS credencial_atualizada_em TIMESTAMPTZ")
    # Sem `DEFAULT` fixo (precisa copiar de outra coluna, por linha) — só
    # preenche quem ainda não tem (`NULL`), nunca sobrescreve uma data já
    # calculada; roda 1x por processo, igual o resto desta função.
    cursor.execute(
        "UPDATE provedores_llm SET credencial_atualizada_em = criado_em WHERE credencial_atualizada_em IS NULL"
    )
    _tabela_garantida = True


def _carregar_json(valor):
    return json.loads(valor) if isinstance(valor, str) else valor


def _linha_para_provedor(linha: tuple) -> ProvedorLLM:
    (
        id_,
        nome,
        tipo_conexao,
        base_url,
        api_key,
        projeto_id,
        modelo,
        estilo_api,
        preco_entrada_por_1k,
        preco_saida_por_1k,
        moeda,
        capacidades,
        credenciais_extra,
        credencial_atualizada_em,
        criado_em,
    ) = linha
    return ProvedorLLM(
        id=id_,
        nome=nome,
        tipo_conexao=tipo_conexao,
        base_url=base_url,
        api_key=api_key or "",
        projeto_id=projeto_id or "",
        modelo=modelo,
        estilo_api=estilo_api,
        preco_entrada_por_1k=Decimal(preco_entrada_por_1k),
        preco_saida_por_1k=Decimal(preco_saida_por_1k),
        moeda=moeda,
        capacidades=_carregar_json(capacidades) if capacidades is not None else ["chat"],
        credenciais_extra=_carregar_json(credenciais_extra),
        # `or criado_em`: só pra uma linha lida ANTES do backfill acima
        # rodar nesse processo (janela mínima); depois da 1ª chamada a
        # `_garantir_tabela`, nunca mais vem `None` do banco.
        credencial_atualizada_em=credencial_atualizada_em or criado_em,
        criado_em=criado_em,
    )


def listar() -> list[ProvedorLLM]:
    """Mais recente primeiro — mesmo critério de `usuarios.listar_usuarios`."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(f"SELECT {_COLUNAS} FROM provedores_llm ORDER BY id DESC")
        linhas = cursor.fetchall()
    return [_linha_para_provedor(linha) for linha in linhas]


def buscar(id_provedor: int) -> ProvedorLLM | None:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(f"SELECT {_COLUNAS} FROM provedores_llm WHERE id = :id", id=id_provedor)
        linha = cursor.fetchone()
    return _linha_para_provedor(linha) if linha else None


def criar(
    *,
    nome: str,
    tipo_conexao: TipoConexao,
    base_url: str,
    api_key: str,
    projeto_id: str,
    modelo: str,
    estilo_api: EstiloApi,
    preco_entrada_por_1k: Decimal,
    preco_saida_por_1k: Decimal,
    moeda: str,
    capacidades: list[Capacidade],
    credenciais_extra: dict | None = None,
) -> ProvedorLLM:
    estilo_api = _ESTILO_API_CONHECIDO.get(modelo.strip(), estilo_api)
    try:
        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute(
                f"""
                INSERT INTO provedores_llm
                    (nome, tipo_conexao, base_url, api_key, projeto_id, modelo, estilo_api,
                     preco_entrada_por_1k, preco_saida_por_1k, moeda, capacidades, credenciais_extra,
                     credencial_atualizada_em, criado_em)
                VALUES (:nome, :tipo_conexao, :base_url, :api_key, :projeto_id, :modelo, :estilo_api,
                        :preco_entrada_por_1k, :preco_saida_por_1k, :moeda,
                        :capacidades::jsonb, :credenciais_extra::jsonb, :agora, :agora)
                RETURNING {_COLUNAS}
                """,
                nome=nome,
                tipo_conexao=tipo_conexao,
                base_url=base_url,
                api_key=api_key or None,
                projeto_id=projeto_id or None,
                modelo=modelo,
                estilo_api=estilo_api,
                preco_entrada_por_1k=preco_entrada_por_1k,
                preco_saida_por_1k=preco_saida_por_1k,
                moeda=moeda,
                capacidades=json.dumps(capacidades),
                credenciais_extra=json.dumps(credenciais_extra) if credenciais_extra is not None else None,
                agora=datetime.now(UTC),
            )
            linha = cursor.fetchone()
    except DatabaseError as erro:
        if eh_erro_valor_duplicado(erro):
            raise ProvedorLlmJaExiste(f'Já existe um provedor cadastrado com o nome "{nome}".') from erro
        raise
    return _linha_para_provedor(linha)


def _deve_renovar_credencial(campos: dict) -> bool:
    """`True` quando `api_key`/`credenciais_extra` vêm preenchidos de
    verdade nesta edição — não toda edição (mudar só o preço, por
    exemplo, não conta) e não quando vêm vazios/`None` (é o caso de
    "deixei em branco pra manter a credencial atual", que este módulo
    também não deveria contar como renovação)."""
    return any(campos.get(campo) for campo in _CAMPOS_CREDENCIAL)


def atualizar(id_provedor: int, **campos) -> ProvedorLLM | None:
    """Só grava os campos passados (mesmo padrão de `_gravar` já usado no
    projeto) — `campos` vazio simplesmente não executa nenhum UPDATE.
    `api_key`/`projeto_id` ausentes do corpo mantêm o valor atual (é assim
    que o editar-sem-re-digitar-a-chave funciona — decidido pela rota, não
    aqui: esta função só reflete o que recebe). `capacidades`/
    `credenciais_extra` (JSONB) passam por `json.dumps` + `::jsonb` antes
    de ir pro bind — os demais campos vão direto, sem cast. Trocar
    `api_key`/`credenciais_extra` por um valor novo também bate
    `credencial_atualizada_em` pra agora, mesmo que ninguém tenha pedido
    isso explicitamente (ver `_deve_renovar_credencial`). Trocar pra um
    `modelo` CONHECIDO (`_ESTILO_API_CONHECIDO`) também corrige o
    `estilo_api` sozinho, mesmo que quem chamou não tenha mandado esse
    campo nesta edição (ou tenha mandado um valor errado) — é assim que a
    tela reenviando um formulário desatualizado não consegue regravar um
    `estilo_api` errado por cima de um certo."""
    if not campos:
        return buscar(id_provedor)
    if "modelo" in campos:
        estilo_conhecido = _ESTILO_API_CONHECIDO.get(str(campos["modelo"]).strip())
        if estilo_conhecido is not None:
            campos = {**campos, "estilo_api": estilo_conhecido}
    campos_finais = dict(campos)
    if _deve_renovar_credencial(campos):
        campos_finais["credencial_atualizada_em"] = datetime.now(UTC)
    campos_bind = dict(campos_finais)
    for campo in _CAMPOS_JSON:
        if campo in campos_bind and campos_bind[campo] is not None:
            campos_bind[campo] = json.dumps(campos_bind[campo])
    try:
        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            atribuicoes = ", ".join(
                f"{campo} = :{campo}::jsonb" if campo in _CAMPOS_JSON else f"{campo} = :{campo}"
                for campo in campos_finais
            )
            cursor.execute(
                f"UPDATE provedores_llm SET {atribuicoes} WHERE id = :id RETURNING {_COLUNAS}",
                id=id_provedor,
                **campos_bind,
            )
            linha = cursor.fetchone()
    except DatabaseError as erro:
        if eh_erro_valor_duplicado(erro):
            raise ProvedorLlmJaExiste(f'Já existe um provedor cadastrado com o nome "{campos.get("nome")}".') from erro
        raise
    return _linha_para_provedor(linha) if linha else None


def remover(id_provedor: int) -> bool:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("DELETE FROM provedores_llm WHERE id = :id", id=id_provedor)
        return cursor.rowcount > 0


def custo_estimado(tokens_entrada: int, tokens_saida: int, provedor: ProvedorLLM) -> Decimal:
    return (Decimal(tokens_entrada) / 1000) * provedor.preco_entrada_por_1k + (
        Decimal(tokens_saida) / 1000
    ) * provedor.preco_saida_por_1k


def tipo_conexao_valido(valor: str) -> bool:
    return valor in _TIPOS_CONEXAO_VALIDOS


def estilo_api_valido(valor: str) -> bool:
    return valor in _ESTILOS_API_VALIDOS


def capacidades_validas(valores: list) -> bool:
    """Lista não-vazia, só com `"chat"`/`"embedding"`, sem duplicata."""
    return (
        isinstance(valores, list)
        and bool(valores)
        and len(valores) == len(set(valores))
        and all(valor in _CAPACIDADES_VALIDAS for valor in valores)
    )
