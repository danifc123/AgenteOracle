"""Configurações globais de IA que não são "qual LLM está cadastrado"
(isso mora em `tools/ia/provedores_llm.py`) — hoje só o ponteiro de qual
LLM cadastrado está ATIVO agora, e o teto diário de tokens. Editável sem
reiniciar o servidor. Lida por `tools/ia/cliente_protegido.py` pra
QUALQUER domínio que os chamar — hoje TI e RH (uma troca aqui afeta os
dois juntos). Financeiro/Auditoria ainda não estão ligados nisso: tocam
dado real do Oracle, e `config.py::validar_ollama_host_seguro` bloqueia
esses dois domínios de IA remota até o fornecedor ser validado pra esse
tipo de dado — não é TI-específico de propósito, por isso mora em
`tools/ia/`, não em `tools/ti/`."""

from agente_oracle.db.connection import get_postgres_connection

_tabela_garantida = False

_CHAVE_PROVEDOR_LLM_ATIVO_ID = "provedor_llm_ativo_id"
_CHAVE_TETO_TOKENS_DIARIO = "teto_tokens_diario"


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


def definir_provedor_llm_ativo_id(valor: int | None) -> None:
    """`None` = nenhum LLM cadastrado ativo — `criar_cliente_protegido`
    cai no Ollama padrão do `.env` nesse caso."""
    _gravar_texto(_CHAVE_PROVEDOR_LLM_ATIVO_ID, "" if valor is None else str(valor))


def provedor_llm_ativo_id() -> int | None:
    bruto = _ler_texto(_CHAVE_PROVEDOR_LLM_ATIVO_ID, padrao="")
    return int(bruto) if bruto else None


def definir_teto_tokens_diario(valor: int) -> None:
    _gravar_texto(_CHAVE_TETO_TOKENS_DIARIO, str(valor))


def teto_tokens_diario() -> int:
    """`0` (padrão) = sem teto. Lido por
    `tools/ia/cliente_protegido.py::ClienteIAProtegido._avisar_teto_tokens`."""
    return int(_ler_texto(_CHAVE_TETO_TOKENS_DIARIO, padrao="0"))
