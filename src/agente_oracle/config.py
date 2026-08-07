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

    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5-coder:7b"

    auth_secret_key: str = ""
    auth_token_horas: int = 12

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
