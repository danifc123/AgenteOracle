from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Domínios que hoje chamam IA — usado pra host/modelo por domínio (ver
# `ollama_host_do_dominio` abaixo) e pro client protegido de `tools/ia/`.
DominioIA = Literal["ti", "financeiro", "rh", "auditoria"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    db_backend: Literal["oracle", "postgres"] = "oracle"

    oracle_dsn: str = ""
    oracle_user: str = ""
    oracle_password: str = ""
    oracle_pool_min: int = 1
    oracle_pool_max: int = 4
    oracle_pool_increment: int = 1
    oracle_client_lib_dir: str | None = None

    # Conexão separada e independente com o Oracle do Protheus (login/
    # auditoria de usuário, ver `tools/ti/protheus_login.py`) — nunca
    # reaproveita as credenciais do STAGE acima. Opcional: sem `protheus_dsn`
    # configurado, a detecção de segurança do TI simplesmente não usa essa
    # fonte, sem quebrar nada (ver `db/connection.py::protheus_configurado`).
    protheus_dsn: str = ""
    protheus_user: str = ""
    protheus_password: str = ""
    protheus_schema: str = "PROTHMG"
    protheus_pool_min: int = 1
    protheus_pool_max: int = 2
    protheus_pool_increment: int = 1

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "agente_oracle"
    postgres_user: str = "postgres"
    postgres_password: str = ""
    postgres_pool_min: int = 1
    postgres_pool_max: int = 4

    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8000

    # Origens (frontend) que podem chamar a API pelo navegador — separadas por
    # vírgula. Sem isso no allow-list, o navegador bloqueia a resposta mesmo
    # com token válido (CORS não é autenticação, é sobre "que site" pode ler
    # a resposta pelo navegador).
    allowed_origins: str = "http://localhost:4200,http://127.0.0.1:4200"

    # `OLLAMA_HOST` apontando pra fora da máquina (GPU alugada, IA em nuvem)
    # só é seguro com `DB_BACKEND=postgres` (banco fictício) — com
    # `DB_BACKEND=oracle` (dado real da Conceito), `validar_ollama_host_seguro`
    # abaixo bloqueia a subida do servidor de propósito.
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_embedding_model: str = "nomic-embed-text"

    # Override por domínio (`DominioIA`) — vazio usa o valor global acima
    # (`ollama_host_do_dominio`/`ollama_model_do_dominio`/`ollama_api_key_do_dominio`
    # resolvem isso). Aditivo: não preencher nada mantém o comportamento de
    # sempre, um host global só. `OLLAMA_HOST_TI` remoto é sempre permitido
    # (TI não toca Oracle); os outros três continuam bloqueados com
    # `DB_BACKEND=oracle` — ver `validar_ollama_host_seguro`.
    ollama_host_ti: str = ""
    ollama_model_ti: str = ""
    ollama_api_key_ti: str = ""
    ollama_host_financeiro: str = ""
    ollama_model_financeiro: str = ""
    ollama_api_key_financeiro: str = ""
    ollama_host_rh: str = ""
    ollama_model_rh: str = ""
    ollama_api_key_rh: str = ""
    ollama_host_auditoria: str = ""
    ollama_model_auditoria: str = ""
    ollama_api_key_auditoria: str = ""

    auth_secret_key: str = ""
    # 8h = uma jornada de trabalho — depois disso o token expira sozinho e o
    # usuário precisa logar de novo, mesmo com a aba aberta o tempo todo.
    auth_token_horas: int = 8

    # Integração real com o GLPI (service desk, `tools/ti/glpi.py`) — não
    # existe mais cliente mock. Sem `glpi_base_url` preenchida, o servidor
    # ainda sobe normal (outros módulos não dependem disso), mas a
    # funcionalidade de TI (Auditoria de Chamados, webhook) não funciona
    # até isso ser configurado.
    #
    # Autenticação confirmada contra a instância real: grant `password`
    # (client_id/secret do client OAuth + usuário/senha de uma conta de
    # serviço), não `client_credentials` — testado e confirmado que esse
    # GLPI rejeita token de client_credentials puro (sem usuário por trás)
    # em qualquer endpoint de recurso. Em homologação, `glpi_username`/
    # `glpi_password` apontam pra uma conta compartilhada com outra
    # integração ("api.ebarn") só pra teste; produção deve trocar por uma
    # conta de serviço dedicada a este agente.
    glpi_base_url: str = ""
    glpi_client_id: str = ""
    glpi_client_secret: str = ""
    glpi_username: str = ""
    glpi_password: str = ""
    glpi_webhook_secret: str = ""

    # API Legada do GLPI (`apirest.php`, autenticação por sessão + App-Token
    # — mecanismo diferente do OAuth acima) — usada só pra marcar o motivo
    # de pendência "Aguardando usuário" (`PendingReason_Item`), porque a API
    # nova (v2.3) só lê essa informação, nunca escreve (confirmado no
    # código-fonte do GLPI: só existe rota GET pra isso). OPCIONAL: sem
    # isso configurado, `ClienteGLPIReal` continua marcando o chamado como
    # "Pendente" (status genérico), só não consegue marcar o motivo
    # específico — ver `tools/ti/glpi.py::ClienteGLPIReal.
    # _marcar_aguardando_usuario`.
    glpi_legacy_api_url: str = ""
    glpi_legacy_app_token: str = ""
    glpi_legacy_user_token: str = ""

    # Id do usuário GLPI da própria conta de serviço (a mesma de
    # `glpi_username`/`glpi_password` acima) — confirmado ao vivo contra a
    # instância real que um chamado sem NINGUÉM atribuído (usuário, não só
    # Group) rejeita silenciosamente qualquer troca de status. Usado só
    # como "segurador de lugar": atribuído no instante de trocar o status
    # pela primeira vez, depois desatribuído — ver
    # `server/ti/chamados.py::processar_chamado_novo`. OPCIONAL: sem isso,
    # `processar_chamado_novo` pula esse passo (mesmo espírito dos outros
    # campos de TI opcionais).
    glpi_conta_ia_id: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origem.strip() for origem in self.allowed_origins.split(",") if origem.strip()]


settings = Settings()

TAMANHO_MINIMO_AUTH_SECRET_KEY = 32


def ollama_api_key_do_dominio(settings: Settings, dominio: DominioIA) -> str:
    return getattr(settings, f"ollama_api_key_{dominio}")


def ollama_host_do_dominio(settings: Settings, dominio: DominioIA) -> str:
    """Host do domínio se configurado (`OLLAMA_HOST_TI` etc.), senão o host
    global — aditivo, sem override nenhum todo domínio cai no `ollama_host`
    de sempre."""
    return getattr(settings, f"ollama_host_{dominio}") or settings.ollama_host


def ollama_model_do_dominio(settings: Settings, dominio: DominioIA) -> str:
    return getattr(settings, f"ollama_model_{dominio}") or settings.ollama_model


def validar_auth_secret_key(settings: Settings) -> None:
    """Falha rápido na inicialização do servidor se `AUTH_SECRET_KEY` não
    estiver configurada (ou for curta demais pra ter entropia suficiente).
    Sem essa checagem, o servidor subia normalmente assinando e verificando
    token com uma chave vazia — qualquer um consegue forjar um token válido
    sabendo disso, já que a chave "secreta" é uma string vazia conhecida.
    Chamada só em `server/app.py:main()` (o processo real do servidor) — não
    roda ao simplesmente importar este módulo, então não afeta testes nem
    scripts que só precisam de outras configurações."""
    if len(settings.auth_secret_key) < TAMANHO_MINIMO_AUTH_SECRET_KEY:
        raise RuntimeError(
            f"AUTH_SECRET_KEY não está configurada, ou tem menos de "
            f"{TAMANHO_MINIMO_AUTH_SECRET_KEY} caracteres. Gere um valor aleatório com "
            '`python -c "import secrets; print(secrets.token_hex(32))"` e defina no .env '
            "antes de subir o servidor — sem uma chave forte, qualquer pessoa consegue "
            "forjar um token de login válido."
        )


def validar_glpi_configurado(settings: Settings) -> None:
    """Sem `GLPI_BASE_URL` preenchida, não valida nada — não trava a subida
    do servidor pros times que não mexem em TI (mesmo espírito de
    `protheus_configurado()`), só a própria funcionalidade de TI não
    funciona até isso ser configurado (não existe mais cliente mock de
    fallback). Só quando alguém preenche `GLPI_BASE_URL` (decidindo usar o
    GLPI real) é que as 4 credenciais do grant `password` (client_id/secret
    + usuário/senha da conta de serviço — ver comentário acima do campo)
    viram obrigatórias, e o segredo do webhook precisa da mesma entropia
    mínima de `AUTH_SECRET_KEY` — mesmo espírito de `validar_auth_secret_key`.
    Chamada só em `server/app.py:main()`, nunca ao importar este módulo."""
    if not settings.glpi_base_url:
        return

    faltando = [
        nome
        for nome, valor in (
            ("GLPI_CLIENT_ID", settings.glpi_client_id),
            ("GLPI_CLIENT_SECRET", settings.glpi_client_secret),
            ("GLPI_USERNAME", settings.glpi_username),
            ("GLPI_PASSWORD", settings.glpi_password),
        )
        if not valor
    ]
    if faltando:
        raise RuntimeError(
            f"GLPI_BASE_URL está configurada, mas {', '.join(faltando)} não — todas as "
            "credenciais (client OAuth + usuário/senha da conta de serviço) são "
            "obrigatórias pra autenticar contra o GLPI real (grant `password`)."
        )

    if len(settings.glpi_webhook_secret) < TAMANHO_MINIMO_AUTH_SECRET_KEY:
        raise RuntimeError(
            f"GLPI_WEBHOOK_SECRET precisa ter pelo menos {TAMANHO_MINIMO_AUTH_SECRET_KEY} "
            'caracteres. Gere um valor aleatório com `python -c "import secrets; '
            'print(secrets.token_hex(32))"` e defina no .env antes de subir o servidor.'
        )


_MARCADORES_OLLAMA_HOST_LOCAL = ("127.0.0.1", "localhost", "::1")


# TI de propósito fora dessa lista: confirmado no código que os agentes de TI
# (`agent/ti/qualidade_chamado.py`, `roteamento_chamado.py`, `deteccao_seguranca.py`)
# nunca leem dado do Oracle — só GLPI e Postgres próprio. É por isso que dá
# pra liberar `OLLAMA_HOST_TI` remoto mesmo com `DB_BACKEND=oracle` sem
# validar nada: não existe dado real da Conceito nesse caminho pra proteger.
# TI de propósito fora dessa lista: confirmado no código que os agentes de TI
# (`agent/ti/qualidade_chamado.py`, `roteamento_chamado.py`, `deteccao_seguranca.py`)
# nunca leem dado do Oracle — só GLPI e Postgres próprio. É por isso que dá
# pra liberar `OLLAMA_HOST_TI` remoto mesmo com `DB_BACKEND=oracle` sem
# validar nada: não existe dado real da Conceito nesse caminho pra proteger.
_DOMINIOS_COM_RISCO_ORACLE: tuple[DominioIA, ...] = ("financeiro", "rh", "auditoria")


def _eh_host_local(host: str) -> bool:
    host_normalizado = host.lower()
    return any(marcador in host_normalizado for marcador in _MARCADORES_OLLAMA_HOST_LOCAL)


def validar_ollama_host_seguro(settings: Settings) -> None:
    """Falha rápido na inicialização se `DB_BACKEND=oracle` (dado real da
    Conceito) e `OLLAMA_HOST` (ou um `OLLAMA_HOST_<DOMÍNIO>` específico)
    apontar pra fora da própria máquina — protege contra dado real sair pra
    uma IA em nuvem/servidor remoto só porque alguém trocou pra um modelo
    maior pra testar algo e esqueceu de voltar pro host local antes de
    reconectar no Oracle de verdade. Com `DB_BACKEND=postgres` (banco
    fictício, sem dado real da empresa) não bloqueia nada — ali é seguro usar
    qualquer IA, local ou remota. Mesmo espírito de `validar_auth_secret_key`:
    só roda em `server/app.py:main()`, nunca ao importar este módulo, então
    não afeta teste nem script.

    O global (`OLLAMA_HOST`) é validado primeiro, exatamente como sempre foi
    — quem nunca configurou nada por domínio continua com o mesmo
    comportamento de antes. Só depois checa, um a um, o override explícito
    de `_DOMINIOS_COM_RISCO_ORACLE` (financeiro/RH/auditoria — domínio sem
    override nenhum já caiu no global e não é checado de novo). `ti` fica
    de fora dessa lista de propósito: confirmado no código que os agentes de
    TI nunca leem dado do Oracle, então `OLLAMA_HOST_TI` pode ser remoto sem
    checagem nenhuma, mesmo com `DB_BACKEND=oracle` — é o que permite ligar
    só o TI numa IA em nuvem sem abrir os outros domínios."""
    if settings.db_backend != "oracle":
        return

    if not _eh_host_local(settings.ollama_host):
        raise RuntimeError(
            f"OLLAMA_HOST está configurado pra um endereço fora desta máquina "
            f"('{settings.ollama_host}') enquanto DB_BACKEND=oracle (dado real da "
            "Conceito) — isso mandaria dado real da empresa pra uma IA remota/em "
            "nuvem. Ou volte OLLAMA_HOST pra um endereço local (ex: "
            "http://127.0.0.1:11434), ou troque DB_BACKEND=postgres (banco "
            "fictício local) antes de usar uma IA remota."
        )

    for dominio in _DOMINIOS_COM_RISCO_ORACLE:
        host_dominio = getattr(settings, f"ollama_host_{dominio}")
        if host_dominio and not _eh_host_local(host_dominio):
            raise RuntimeError(
                f"OLLAMA_HOST_{dominio.upper()} está configurado pra um endereço fora desta "
                f"máquina ('{host_dominio}') enquanto DB_BACKEND=oracle (dado real da Conceito) "
                f"— confirme que o domínio '{dominio}' realmente não usa dado do Oracle antes de "
                "liberar isso, ou volte esse host pra um endereço local."
            )
