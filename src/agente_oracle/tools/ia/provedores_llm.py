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

`tipo_conexao` é fechado a duas opções de propósito — são os dois
formatos que o projeto sabe falar (`ollama.AsyncClient` nativo e
`ClienteOpenAICompativel`, ver `tools/ia/cliente_protegido.py`). Um
provedor genuinamente novo só entra sem código se falar um desses dois
protocolos (o que cobre a maioria dos provedores de IA em nuvem hoje,
inclusive a própria OCI) — um terceiro protocolo ainda exigiria código
novo, isso aqui não resolve esse caso.

Preço é opcional (`0` = sem custo, é o padrão) — inclusive pra Ollama,
que não tem custo real em dinheiro: o campo existe igual pra todo mundo,
quem cadastra decide se preenche. A conversão de tokens pra custo usa
sempre o preço CADASTRADO HOJE, não um preço congelado no momento de cada
chamada — mais simples, e como não convertemos moeda (cada linha só tem
um prefixo de exibição, `moeda`), o custo é sempre mostrado por linha,
nunca somado entre provedores com moedas diferentes."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from agente_oracle.db.connection import DatabaseError, eh_erro_valor_duplicado, get_postgres_connection

TipoConexao = Literal["ollama", "openai_compativel"]
EstiloApi = Literal["chat_completions", "responses"]

_TIPOS_CONEXAO_VALIDOS: tuple[TipoConexao, ...] = ("ollama", "openai_compativel")
_ESTILOS_API_VALIDOS: tuple[EstiloApi, ...] = ("chat_completions", "responses")

_tabela_garantida = False

_COLUNAS = (
    "id, nome, tipo_conexao, base_url, api_key, projeto_id, modelo, estilo_api, "
    "preco_entrada_por_1k, preco_saida_por_1k, moeda, criado_em"
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
    _tabela_garantida = True


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
) -> ProvedorLLM:
    try:
        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute(
                f"""
                INSERT INTO provedores_llm
                    (nome, tipo_conexao, base_url, api_key, projeto_id, modelo, estilo_api,
                     preco_entrada_por_1k, preco_saida_por_1k, moeda, criado_em)
                VALUES (:nome, :tipo_conexao, :base_url, :api_key, :projeto_id, :modelo, :estilo_api,
                        :preco_entrada_por_1k, :preco_saida_por_1k, :moeda, :agora)
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
                agora=datetime.now(UTC),
            )
            linha = cursor.fetchone()
    except DatabaseError as erro:
        if eh_erro_valor_duplicado(erro):
            raise ProvedorLlmJaExiste(f'Já existe um provedor cadastrado com o nome "{nome}".') from erro
        raise
    return _linha_para_provedor(linha)


def atualizar(id_provedor: int, **campos) -> ProvedorLLM | None:
    """Só grava os campos passados (mesmo padrão de `_gravar` já usado no
    projeto) — `campos` vazio simplesmente não executa nenhum UPDATE.
    `api_key`/`projeto_id` ausentes do corpo mantêm o valor atual (é assim
    que o editar-sem-re-digitar-a-chave funciona — decidido pela rota, não
    aqui: esta função só reflete o que recebe)."""
    if not campos:
        return buscar(id_provedor)
    try:
        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            atribuicoes = ", ".join(f"{campo} = :{campo}" for campo in campos)
            cursor.execute(
                f"UPDATE provedores_llm SET {atribuicoes} WHERE id = :id RETURNING {_COLUNAS}",
                id=id_provedor,
                **campos,
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
