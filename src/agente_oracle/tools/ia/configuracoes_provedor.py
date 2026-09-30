"""Configurações globais de IA que não são "qual LLM está cadastrado"
(isso mora em `tools/ia/provedores_llm.py`) — dois ponteiros de qual LLM
cadastrado está ATIVO agora (um pra chat, outro pra embedding —
independentes, porque nem todo provedor sabe fazer as duas coisas,
`capacidades`), mais o teto diário de tokens (esse sim, POR DOMÍNIO —
ver `teto_tokens_diario` abaixo). Editável sem reiniciar o servidor. Os
ponteiros de provedor ativo são lidos por `tools/ia/cliente_protegido.py`
pra QUALQUER domínio que os chamar — hoje TI e RH (uma troca aqui afeta
os dois juntos; só o teto é isolado por domínio). Financeiro/Auditoria
ainda não estão ligados nisso: tocam dado real do Oracle, e
`config.py::validar_ollama_host_seguro` bloqueia esses dois domínios de
IA remota até o fornecedor ser validado pra esse tipo de dado — não é
TI-específico de propósito, por isso mora em `tools/ia/`, não em
`tools/ti/`."""

from agente_oracle.db.connection import get_postgres_connection

_tabela_garantida = False

_CHAVE_PROVEDOR_LLM_ATIVO_ID = "provedor_llm_ativo_id"
_CHAVE_PROVEDOR_LLM_EMBEDDING_ATIVO_ID = "provedor_llm_embedding_ativo_id"


def _chave_teto_tokens_diario(dominio: str) -> str:
    # Uma chave por domínio (`teto_tokens_diario_ti`, `_rh`, ...) na mesma
    # tabela chave-valor genérica — cada departamento tem seu próprio
    # teto, sem tabela nova nem migração (ver `server/ia/teto_tokens.py`
    # pra onde isso vira trava de verdade, não só aviso).
    return f"teto_tokens_diario_{dominio}"


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


def definir_provedor_llm_embedding_ativo_id(valor: int | None) -> None:
    """Ponteiro INDEPENDENTE de `definir_provedor_llm_ativo_id` (chat) —
    nem todo provedor sabe fazer as duas coisas (`capacidades`), e travar
    os dois no mesmo ponteiro impedia ter um modelo de chat e um de
    embedding ativos ao mesmo tempo. `None` = nenhum embedding cadastrado
    ativo — `tools/ia/cliente_protegido.py::criar_cliente_embedding_protegido`
    cai no provedor de CHAT ativo nesse caso (mesmo comportamento de antes
    desse ponteiro existir)."""
    _gravar_texto(_CHAVE_PROVEDOR_LLM_EMBEDDING_ATIVO_ID, "" if valor is None else str(valor))


def provedor_llm_embedding_ativo_id() -> int | None:
    bruto = _ler_texto(_CHAVE_PROVEDOR_LLM_EMBEDDING_ATIVO_ID, padrao="")
    return int(bruto) if bruto else None


def definir_teto_tokens_diario(dominio: str, valor: int) -> None:
    _gravar_texto(_chave_teto_tokens_diario(dominio), str(valor))


def teto_tokens_diario(dominio: str) -> int:
    """`0` (padrão) = sem teto pra esse domínio. Lido por
    `tools/ia/cliente_protegido.py::ClienteIAProtegido` antes de cada
    chamada real, pra decidir se bloqueia (ver `TetoTokensExcedidoError`)."""
    return int(_ler_texto(_chave_teto_tokens_diario(dominio), padrao="0"))
