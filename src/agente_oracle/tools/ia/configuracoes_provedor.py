"""Escolha ATIVA de provedor/modelo de IA (`configuracoes_ia`) — editável
sem reiniciar o servidor, pela tela de Configurações do TI
(`server/ti/configuracoes.py`, rota `/api/ti/configuracoes` — é o painel
que o time de TI já usa, não existe uma tela própria pro RH). Lida por
`tools/ia/cliente_protegido.py::criar_cliente_protegido`/`modelo_ia_ativo`
pra QUALQUER domínio que os chamar — hoje TI e RH (uma troca aqui afeta os
dois juntos). Financeiro/Auditoria ainda não estão ligados nisso: tocam
dado real do Oracle, e `config.py::validar_ollama_host_seguro` bloqueia
esses dois domínios de IA remota até o fornecedor ser validado pra esse
tipo de dado — não é TI-específico de propósito, por isso mora em
`tools/ia/`, não em `tools/ti/`."""

from agente_oracle.config import ProvedorIA
from agente_oracle.db.connection import get_postgres_connection

_tabela_garantida = False

_CHAVE_MODELO_IA = "modelo_ia"
_CHAVE_PROVEDOR_IA = "provedor_ia"
_CHAVE_TETO_TOKENS_DIARIO = "teto_tokens_diario"

PROVEDOR_IA_PADRAO: ProvedorIA = "ollama"


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracoes_ia (
            chave VARCHAR PRIMARY KEY,
            valor_texto VARCHAR
        )
    """)
    _tabela_garantida = True


def _gravar_texto(chave: str, valor: str) -> None:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "UPDATE configuracoes_ia SET valor_texto = :valor WHERE chave = :chave", valor=valor, chave=chave
        )
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT INTO configuracoes_ia (chave, valor_texto) VALUES (:chave, :valor)",
                chave=chave,
                valor=valor,
            )


def _ler_texto(chave: str, padrao: str) -> str:
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("SELECT valor_texto FROM configuracoes_ia WHERE chave = :chave", chave=chave)
        linha = cursor.fetchone()
    return linha[0] if linha and linha[0] is not None else padrao


def definir_modelo_ia(valor: str) -> None:
    _gravar_texto(_CHAVE_MODELO_IA, valor)


def definir_provedor_ia(valor: ProvedorIA) -> None:
    _gravar_texto(_CHAVE_PROVEDOR_IA, valor)


def modelo_ia() -> str:
    """Vazio = usa o modelo padrão do provedor ativo — ver
    `tools/ia/cliente_protegido.py::modelo_ia_ativo`."""
    return _ler_texto(_CHAVE_MODELO_IA, padrao="")


def provedor_ia() -> ProvedorIA:
    return _ler_texto(_CHAVE_PROVEDOR_IA, padrao=PROVEDOR_IA_PADRAO)


def definir_teto_tokens_diario(valor: int) -> None:
    _gravar_texto(_CHAVE_TETO_TOKENS_DIARIO, str(valor))


def teto_tokens_diario() -> int:
    """`0` (padrão) = sem teto — mesmo espírito de "vazio = sem restrição"
    que `modelo_ia` já usa. Lido por
    `tools/ia/cliente_protegido.py::ClienteIAProtegido._avisar_teto_tokens`."""
    return int(_ler_texto(_CHAVE_TETO_TOKENS_DIARIO, padrao="0"))
