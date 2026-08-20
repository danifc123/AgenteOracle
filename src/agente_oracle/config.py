from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    auth_secret_key: str = ""
    # 8h = uma jornada de trabalho — depois disso o token expira sozinho e o
    # usuário precisa logar de novo, mesmo com a aba aberta o tempo todo.
    auth_token_horas: int = 8

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origem.strip() for origem in self.allowed_origins.split(",") if origem.strip()]


settings = Settings()

TAMANHO_MINIMO_AUTH_SECRET_KEY = 32


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


_MARCADORES_OLLAMA_HOST_LOCAL = ("127.0.0.1", "localhost", "::1")


def validar_ollama_host_seguro(settings: Settings) -> None:
    """Falha rápido na inicialização se `DB_BACKEND=oracle` (dado real da
    Conceito) e `OLLAMA_HOST` apontar pra fora da própria máquina — protege
    contra dado real sair pra uma IA em nuvem/servidor remoto só porque
    alguém trocou pra um modelo maior pra testar algo e esqueceu de voltar
    pro host local antes de reconectar no Oracle de verdade. Com
    `DB_BACKEND=postgres` (banco fictício, sem dado real da empresa) não
    bloqueia nada — ali é seguro usar qualquer IA, local ou remota. Mesmo
    espírito de `validar_auth_secret_key`: só roda em `server/app.py:main()`,
    nunca ao importar este módulo, então não afeta teste nem script."""
    if settings.db_backend != "oracle":
        return

    host = settings.ollama_host.lower()
    if any(marcador in host for marcador in _MARCADORES_OLLAMA_HOST_LOCAL):
        return

    raise RuntimeError(
        f"OLLAMA_HOST está configurado pra um endereço fora desta máquina "
        f"('{settings.ollama_host}') enquanto DB_BACKEND=oracle (dado real da "
        "Conceito) — isso mandaria dado real da empresa pra uma IA remota/em "
        "nuvem. Ou volte OLLAMA_HOST pra um endereço local (ex: "
        "http://127.0.0.1:11434), ou troque DB_BACKEND=postgres (banco "
        "fictício local) antes de usar uma IA remota."
    )
