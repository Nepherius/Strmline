from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REQUIRED_SETUP_FIELDS = [
    "base_url",
    "database_url",
    "library_root",
    "tmdb_api_key",
    "torbox_api_key",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="STRMLINE_",
        extra="ignore",
    )

    service_name: str = "Strmline"
    version: str = "0.1.0"
    base_url: str | None = None
    database_url: str | None = None
    library_root: Path | None = None
    tmdb_api_key: SecretStr | None = None
    torbox_api_key: SecretStr | None = None
    torbox_base_url: str = Field(default="https://api.torbox.app/v1/api")
    outbound_timeout_seconds: float = Field(default=20.0, gt=0)

    def missing_setup_fields(self) -> list[str]:
        return [
            field_name for field_name in REQUIRED_SETUP_FIELDS if getattr(self, field_name) is None
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
