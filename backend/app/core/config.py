"""Application settings loaded from environment variables (.env in local development)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_timezone: str = "Europe/Zagreb"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Database. The API connects with the least-privileged login role, never the owner.
    database_host: str = "localhost"
    database_port: int = 5432
    postgres_db: str = "prostoriq"
    database_user: str = "prostoriq_api"
    database_password: SecretStr = SecretStr("")
    database_url_override: str | None = Field(default=None, alias="DATABASE_URL")

    # Import pipeline. Runs as the "pipeline" login role, never the API role or owner.
    pipeline_database_url: str | None = Field(default=None, alias="PIPELINE_DATABASE_URL")
    config_dir: Path = _REPO_ROOT / "config"
    raw_storage_dir: Path = _REPO_ROOT / "data" / "raw"

    # Used later for signing comparison-basis tokens (ADR03). Never logged.
    app_hmac_secret: SecretStr = SecretStr("")

    # Only used in development (Vite dev server). Production is same-origin, no CORS.
    allowed_origins: list[str] = ["http://localhost:5173"]

    public_rate_limit_per_minute: int = 30
    max_json_body_bytes: int = 64 * 1024

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        password = self.database_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.database_user}:{password}"
            f"@{self.database_host}:{self.database_port}/{self.postgres_db}"
        )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
