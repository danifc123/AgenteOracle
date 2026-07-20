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

    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"


settings = Settings()
