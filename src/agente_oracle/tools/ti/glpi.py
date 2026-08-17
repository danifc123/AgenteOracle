"""Chamados de service desk (GLPI) — hoje sem integração real, só um
cliente mock (`ClienteGLPIMock`) guardado numa tabela própria no Postgres,
mesmo padrão de `tools/rh/candidatos.py` (`CREATE TABLE IF NOT EXISTS`,
sem migração separada, seed de exemplo se a tabela nascer vazia).

`ClienteGLPI` é a interface que `agent/ti/qualidade_chamado.py` e
`server/ti/chamados.py` realmente usam — pensada já no formato de uma
integração de verdade (`titulo`≈`name`, `descricao`≈`content` do GLPI),
pra quando existir credencial/OAuth2 client cadastrado no GLPI de
verdade, só precisar trocar `ClienteGLPIMock` por um `ClienteGLPIReal`
(via `httpx`, já dependência transitiva do projeto, contra
`/api.php/v2/Ticket` — API REST v2 do GLPI, autenticação OAuth2 password
grant em `/api.php/token`) sem mexer no agente nem nas telas. A API REST
do GLPI não documenta webhook — só dá pra descobrir chamado novo via
polling, e os endpoints de acompanhamento/mudança de status precisam do
Swagger ao vivo da instância de vocês (`/api.php/doc`) pra confirmar o
formato exato — nenhum dos dois está implementado ainda.

`reportar_usuario` também é mock por enquanto (só marca `reportado_em` —
nenhum e-mail sai de verdade, não existe envio de e-mail configurado
neste projeto ainda). O jeito real de fechar o ciclo (perceber que o
usuário completou o chamado no GLPI e liberar pra fila) também fica pra
depois — só dá pra saber isso consultando a API de novo (polling), sem
webhook disponível; por isso não existe hoje um jeito de um chamado
`aguardando_usuario` voltar sozinho pra `fila_atendimento` nesta versão
mock."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from agente_oracle.db.connection import get_postgres_connection

StatusChamado = Literal["novo", "aguardando_usuario", "fila_atendimento"]

_COLUNAS_CHAMADO = (
    "id, titulo, descricao, categoria, status, solicitante, email, avaliacao_mensagem, "
    "reportado_em, criado_em"
)

_CHAMADOS_EXEMPLO = (
    # (titulo, descricao, categoria, solicitante, email) — mistura proposital de
    # vago (sem sistema/erro/urgência citado) e detalhado, pra demonstração
    # deixar clara a diferença que a IA está enxergando.
    (
        "Computador não liga",
        "meu computador não liga, já tentei de tudo",
        "Hardware",
        "Marcos Andrade",
        "marcos.andrade@empresa.com",
    ),
    (
        "Sistema lento",
        "o sistema está muito lento hoje",
        "Sistemas",
        "Juliana Prado",
        "juliana.prado@empresa.com",
    ),
    (
        "Erro 500 ao gerar relatório de vendas no ERP",
        "Ao clicar em 'Gerar Relatório' na tela de Vendas do ERP, aparece 'Erro 500 - Timeout' depois "
        "de uns 30 segundos. Já tentei em dois computadores diferentes (recepção e financeiro) e o "
        "erro persiste desde ontem à tarde. Preciso desse relatório pra reunião amanhã às 9h.",
        "Sistemas",
        "Carla Nogueira",
        "carla.nogueira@empresa.com",
    ),
    (
        "Impressora não funciona",
        "a impressora do setor não tá imprimindo",
        "Hardware",
        "Eduardo Lima",
        "eduardo.lima@empresa.com",
    ),
    (
        "Solicito acesso à pasta compartilhada Financeiro",
        "Preciso de acesso de leitura à pasta \\\\SERVIDOR\\Financeiro\\Relatorios pra fechar a "
        "prestação de contas do mês. Meu usuário de rede é e.lima, autorizado pelo gerente Roberto "
        "Nunes.",
        "Acessos",
        "Eduardo Lima",
        "eduardo.lima@empresa.com",
    ),
    (
        "Notebook travando direto",
        "meu notebook trava umas 3 vezes por dia, principalmente quando abro o Excel",
        "Hardware",
        "Fernanda Costa",
        "fernanda.costa@empresa.com",
    ),
)

_tabela_garantida = False


@dataclass(frozen=True)
class Chamado:
    id: int
    titulo: str
    descricao: str
    categoria: str
    status: StatusChamado
    solicitante: str
    email: str
    avaliacao_mensagem: str | None
    reportado_em: datetime | None
    criado_em: datetime


class ClienteGLPI(Protocol):
    def listar(self) -> list[Chamado]: ...

    def atualizar_avaliacao(self, chamado_id: int, status: StatusChamado, mensagem: str | None) -> None: ...

    def reportar_usuario(self, chamado_id: int) -> None: ...


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ti_chamados_mock (
            id BIGSERIAL PRIMARY KEY,
            titulo VARCHAR NOT NULL,
            descricao TEXT NOT NULL,
            categoria VARCHAR NOT NULL,
            status VARCHAR NOT NULL DEFAULT 'novo',
            solicitante VARCHAR NOT NULL,
            email VARCHAR NOT NULL,
            avaliacao_mensagem TEXT,
            reportado_em TIMESTAMPTZ,
            criado_em TIMESTAMPTZ NOT NULL
        )
    """)
    cursor.execute("SELECT count(*) FROM ti_chamados_mock")
    (total,) = cursor.fetchone()
    if total == 0:
        agora = datetime.now(UTC)
        for titulo, descricao, categoria, solicitante, email in _CHAMADOS_EXEMPLO:
            cursor.execute(
                """
                INSERT INTO ti_chamados_mock (titulo, descricao, categoria, solicitante, email, criado_em)
                VALUES (:titulo, :descricao, :categoria, :solicitante, :email, :agora)
                """,
                titulo=titulo,
                descricao=descricao,
                categoria=categoria,
                solicitante=solicitante,
                email=email,
                agora=agora,
            )
    _tabela_garantida = True


def _linha_para_chamado(linha: tuple) -> Chamado:
    (
        id_,
        titulo,
        descricao,
        categoria,
        status,
        solicitante,
        email,
        avaliacao_mensagem,
        reportado_em,
        criado_em,
    ) = linha
    return Chamado(
        id=id_,
        titulo=titulo,
        descricao=descricao,
        categoria=categoria,
        status=status,
        solicitante=solicitante,
        email=email,
        avaliacao_mensagem=avaliacao_mensagem,
        reportado_em=reportado_em,
        criado_em=criado_em,
    )


class ClienteGLPIMock:
    """Substitui a API do GLPI por uma tabela Postgres própria — o
    "servidor" desse chamado somos nós mesmos, então as mutações
    (`atualizar_avaliacao`, `reportar_usuario`) são `UPDATE` direto, sem a
    cautela de "nunca alterar dado de terceiro" que vale pra sistema
    externo de verdade (Protheus, e futuramente o GLPI real)."""

    def listar(self) -> list[Chamado]:
        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute(f"SELECT {_COLUNAS_CHAMADO} FROM ti_chamados_mock ORDER BY criado_em DESC")
            linhas = cursor.fetchall()
        return [_linha_para_chamado(linha) for linha in linhas]

    def atualizar_avaliacao(self, chamado_id: int, status: StatusChamado, mensagem: str | None) -> None:
        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute(
                "UPDATE ti_chamados_mock SET status = :status, avaliacao_mensagem = :mensagem WHERE id = :id",
                id=chamado_id,
                status=status,
                mensagem=mensagem,
            )

    def reportar_usuario(self, chamado_id: int) -> None:
        """Marca que o usuário foi avisado — hoje só grava `reportado_em`,
        nenhum e-mail sai de verdade (ver docstring do módulo)."""
        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute(
                "UPDATE ti_chamados_mock SET reportado_em = :agora WHERE id = :id",
                id=chamado_id,
                agora=datetime.now(UTC),
            )
