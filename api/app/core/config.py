from functools import lru_cache
from pathlib import Path
from typing import Literal, Self
from urllib.parse import quote_plus

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REQUIRED_SETUP_FIELDS = [
    "torbox_api_key",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STRMLINE_",
        extra="ignore",
    )

    service_name: str = "Strmline"
    version: str = "0.1.0"
    base_url: str | None = None
    database_url: str | None = None
    postgres_host: str | None = None
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_database: str = "strmline"
    postgres_user: str = "strmline"
    postgres_password: SecretStr | None = None
    app_secret_key: SecretStr | None = None
    secure_cookies: bool | None = None
    static_dir: Path | None = None
    library_root: Path = Path("/library")
    tmdb_api_key: SecretStr | None = None
    torbox_api_key: SecretStr | None = None
    resolver_token: SecretStr | None = None
    playback_mode: Literal["resolver", "direct"] | None = None
    sync_interval_minutes: int | None = Field(default=None, ge=1)
    debug_logging: bool | None = None
    season_auto_complete_enabled: bool | None = None
    season_auto_complete_interval_days: int | None = Field(default=None, ge=1)
    season_auto_complete_allow_uncached: bool | None = None
    season_auto_complete_shows_per_minute: int | None = Field(default=None, ge=1, le=60)
    torbox_base_url: str = Field(default="https://api.torbox.app/v1/api")
    tmdb_base_url: str = Field(default="https://api.themoviedb.org/3")
    anilist_base_url: str = Field(default="https://graphql.anilist.co")
    aiostreams_base_url: SecretStr | None = None
    outbound_timeout_seconds: float = Field(default=20.0, gt=0)
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    cors_methods: tuple[str, ...] = ("GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS")
    cors_headers: tuple[str, ...] = (
        "content-type",
        "authorization",
        "x-requested-with",
        "x-csrf-token",
    )

    def missing_setup_fields(self) -> list[str]:
        return [
            field_name for field_name in REQUIRED_SETUP_FIELDS if getattr(self, field_name) is None
        ]

    @model_validator(mode="after")
    def build_database_url_from_postgres_parts(self) -> Self:
        if self.database_url is not None or self.postgres_host is None:
            return self
        if self.postgres_password is None:
            return self

        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password.get_secret_value())
        database = quote_plus(self.postgres_database)
        self.database_url = (
            f"postgresql+asyncpg://{user}:{password}@"
            f"{self.postgres_host}:{self.postgres_port}/{database}"
        )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
