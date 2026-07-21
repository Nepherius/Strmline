from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import ApplicationSettings, ProviderCredential, ResolverToken
from app.operations.defaults import (
    RESOLVER_CIRCUIT_BREAKER_COOLDOWN_SECONDS,
    RESOLVER_CIRCUIT_BREAKER_FAILURES,
    RESOLVER_CIRCUIT_BREAKER_WINDOW_SECONDS,
    RESOLVER_NEGATIVE_CACHE_SECONDS,
    TORBOX_REQUESTS_PER_MINUTE,
)
from app.security.secrets import SecretBox

SECRET_HINT_SUFFIX_LENGTH = 4
DEFAULT_SYNC_INTERVAL_MINUTES = 360
DEFAULT_SEASON_AUTO_COMPLETE_INTERVAL_DAYS = 1
DEFAULT_SEASON_AUTO_COMPLETE_SHOWS_PER_MINUTE = 1
DEFAULT_PLAYBACK_MODE = "resolver"
GENERATED_RESOLVER_TOKEN_BYTES = 32

SettingSource = Literal["database", "environment"]
ProviderName = Literal["tmdb", "torbox"]
PlaybackMode = Literal["resolver", "direct"]


@dataclass(frozen=True, slots=True)
class SettingsSnapshot:
    base_url: str | None
    library_root: str | None
    movies_enabled: bool
    shows_enabled: bool
    anime_enabled: bool
    playback_mode: PlaybackMode
    sync_interval_minutes: int
    torbox_configured: bool
    tmdb_configured: bool
    resolver_configured: bool
    aiostreams_configured: bool
    debug_logging: bool = False
    season_auto_complete_enabled: bool = False
    season_auto_complete_interval_days: int = DEFAULT_SEASON_AUTO_COMPLETE_INTERVAL_DAYS
    season_auto_complete_allow_uncached: bool = False
    season_auto_complete_shows_per_minute: int = DEFAULT_SEASON_AUTO_COMPLETE_SHOWS_PER_MINUTE
    torbox_requests_per_minute: int = TORBOX_REQUESTS_PER_MINUTE
    resolver_negative_cache_seconds: int = RESOLVER_NEGATIVE_CACHE_SECONDS
    resolver_circuit_breaker_failures: int = RESOLVER_CIRCUIT_BREAKER_FAILURES
    resolver_circuit_breaker_window_seconds: int = RESOLVER_CIRCUIT_BREAKER_WINDOW_SECONDS
    resolver_circuit_breaker_cooldown_seconds: int = RESOLVER_CIRCUIT_BREAKER_COOLDOWN_SECONDS
    base_url_source: SettingSource | None = None
    library_root_source: SettingSource | None = None
    torbox_source: SettingSource | None = None
    tmdb_source: SettingSource | None = None
    resolver_source: SettingSource | None = None
    aiostreams_source: SettingSource | None = None


class AppSettingsUpdate(BaseModel):
    base_url: str | None = Field(default=None, min_length=1)
    movies_enabled: bool | None = None
    shows_enabled: bool | None = None
    anime_enabled: bool | None = None
    playback_mode: PlaybackMode | None = None
    sync_interval_minutes: int | None = Field(default=None, ge=1)
    debug_logging: bool | None = None
    season_auto_complete_enabled: bool | None = None
    season_auto_complete_interval_days: int | None = Field(default=None, ge=1)
    season_auto_complete_allow_uncached: bool | None = None
    season_auto_complete_shows_per_minute: int | None = Field(default=None, ge=1, le=60)
    torbox_requests_per_minute: int | None = Field(default=None, ge=1, le=1000)
    resolver_negative_cache_seconds: int | None = Field(default=None, ge=1, le=300)
    resolver_circuit_breaker_failures: int | None = Field(default=None, ge=1, le=20)
    resolver_circuit_breaker_window_seconds: int | None = Field(default=None, ge=1, le=3600)
    resolver_circuit_breaker_cooldown_seconds: int | None = Field(default=None, ge=1, le=3600)
    torbox_api_key: str | None = Field(default=None, min_length=1)
    tmdb_api_key: str | None = Field(default=None, min_length=1)
    resolver_token: str | None = Field(default=None, min_length=1)
    aiostreams_base_url: str | None = Field(default=None, min_length=1)


class AppSettingsRepository:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def snapshot_with_env(self) -> SettingsSnapshot:
        database_settings = await self._application_settings()
        database_base_url = database_settings.base_url if database_settings is not None else None
        torbox_source = await self._secret_source(
            env_configured=self._settings.torbox_api_key is not None,
            provider="torbox",
            name="api_key",
        )
        tmdb_source = await self._secret_source(
            env_configured=self._settings.tmdb_api_key is not None,
            provider="tmdb",
            name="api_key",
        )
        resolver_source = await self._resolver_source(
            env_configured=self._settings.resolver_token is not None,
        )
        aiostreams_source = await self._secret_source(
            env_configured=self._settings.aiostreams_base_url is not None,
            provider="aiostreams",
            name="base_url",
        )
        return SettingsSnapshot(
            base_url=self._settings.base_url or database_base_url,
            library_root=str(self._settings.library_root),
            movies_enabled=_database_value(database_settings, "movies_enabled", default=True),
            shows_enabled=_database_value(database_settings, "shows_enabled", default=True),
            anime_enabled=_database_value(database_settings, "anime_enabled", default=True),
            playback_mode=(
                self._settings.playback_mode
                if self._settings.playback_mode is not None
                else _database_playback_mode(database_settings)
            ),
            sync_interval_minutes=_env_or_db(
                self._settings.sync_interval_minutes,
                database_settings,
                "sync_interval_minutes",
                default=DEFAULT_SYNC_INTERVAL_MINUTES,
            ),
            debug_logging=_database_value(database_settings, "debug_logging", default=False),
            season_auto_complete_enabled=_env_or_db(
                self._settings.season_auto_complete_enabled,
                database_settings,
                "season_auto_complete_enabled",
                default=False,
            ),
            season_auto_complete_interval_days=_env_or_db(
                self._settings.season_auto_complete_interval_days,
                database_settings,
                "season_auto_complete_interval_days",
                default=DEFAULT_SEASON_AUTO_COMPLETE_INTERVAL_DAYS,
            ),
            season_auto_complete_allow_uncached=_env_or_db(
                self._settings.season_auto_complete_allow_uncached,
                database_settings,
                "season_auto_complete_allow_uncached",
                default=False,
            ),
            season_auto_complete_shows_per_minute=_env_or_db(
                self._settings.season_auto_complete_shows_per_minute,
                database_settings,
                "season_auto_complete_shows_per_minute",
                default=DEFAULT_SEASON_AUTO_COMPLETE_SHOWS_PER_MINUTE,
            ),
            torbox_requests_per_minute=_database_value(
                database_settings,
                "torbox_requests_per_minute",
                default=TORBOX_REQUESTS_PER_MINUTE,
            ),
            resolver_negative_cache_seconds=_database_value(
                database_settings,
                "resolver_negative_cache_seconds",
                default=RESOLVER_NEGATIVE_CACHE_SECONDS,
            ),
            resolver_circuit_breaker_failures=_database_value(
                database_settings,
                "resolver_circuit_breaker_failures",
                default=RESOLVER_CIRCUIT_BREAKER_FAILURES,
            ),
            resolver_circuit_breaker_window_seconds=_database_value(
                database_settings,
                "resolver_circuit_breaker_window_seconds",
                default=RESOLVER_CIRCUIT_BREAKER_WINDOW_SECONDS,
            ),
            resolver_circuit_breaker_cooldown_seconds=_database_value(
                database_settings,
                "resolver_circuit_breaker_cooldown_seconds",
                default=RESOLVER_CIRCUIT_BREAKER_COOLDOWN_SECONDS,
            ),
            torbox_configured=torbox_source is not None,
            tmdb_configured=tmdb_source is not None,
            resolver_configured=resolver_source is not None,
            aiostreams_configured=aiostreams_source is not None,
            base_url_source=_plain_setting_source(
                env_configured=self._settings.base_url is not None,
                database_configured=database_base_url is not None,
            ),
            library_root_source="environment",
            torbox_source=torbox_source,
            tmdb_source=tmdb_source,
            resolver_source=resolver_source,
            aiostreams_source=aiostreams_source,
        )

    async def save(self, update: AppSettingsUpdate) -> SettingsSnapshot:
        await self._save_public_settings(update)
        if update.torbox_api_key is not None:
            await self._save_provider_secret("torbox", "api_key", update.torbox_api_key)
        if update.tmdb_api_key is not None:
            await self._save_provider_secret("tmdb", "api_key", update.tmdb_api_key)
        if update.resolver_token is not None:
            await self._save_resolver_token(update.resolver_token)
            await self._save_provider_secret("resolver", "token", update.resolver_token)
        else:
            await self._ensure_resolver_token()
        if update.aiostreams_base_url is not None:
            await self._save_provider_secret(
                "aiostreams",
                "base_url",
                update.aiostreams_base_url,
            )
        await self._session.flush()
        return await self.snapshot_with_env()

    async def clear_saved_setup(self) -> SettingsSnapshot:
        _ = await self._session.execute(delete(ApplicationSettings))
        _ = await self._session.execute(
            delete(ProviderCredential).where(
                ProviderCredential.provider.in_(("resolver", "torbox", "tmdb")),
                ProviderCredential.credential_name == "api_key",
            )
        )
        _ = await self._session.execute(
            delete(ProviderCredential).where(
                ProviderCredential.provider == "aiostreams",
                ProviderCredential.credential_name == "base_url",
            )
        )
        _ = await self._session.execute(
            delete(ProviderCredential).where(
                ProviderCredential.provider == "resolver",
                ProviderCredential.credential_name == "token",
            )
        )
        _ = await self._session.execute(delete(ResolverToken))
        await self._session.flush()
        return await self.snapshot_with_env()

    async def provider_api_key(self, provider: ProviderName) -> str | None:
        env_secret = self._env_provider_secret(provider)
        if env_secret is not None:
            return env_secret
        credential = await self._provider_credential(provider, "api_key")
        if credential is None:
            return None
        return self._secret_box().open(credential.encrypted_value)

    async def resolver_token_value(self) -> str | None:
        if self._settings.resolver_token is not None:
            return self._settings.resolver_token.get_secret_value()
        credential = await self._provider_credential("resolver", "token")
        if credential is None:
            return None
        return self._secret_box().open(credential.encrypted_value)

    async def _application_settings(self) -> ApplicationSettings | None:
        result = await self._session.execute(
            select(ApplicationSettings).where(ApplicationSettings.id == 1)
        )
        return result.scalar_one_or_none()

    async def _save_public_settings(self, update: AppSettingsUpdate) -> None:
        values = {
            "base_url": update.base_url,
            "movies_enabled": update.movies_enabled,
            "shows_enabled": update.shows_enabled,
            "anime_enabled": update.anime_enabled,
            "playback_mode": update.playback_mode,
            "sync_interval_minutes": update.sync_interval_minutes,
            "debug_logging": update.debug_logging,
            "season_auto_complete_enabled": update.season_auto_complete_enabled,
            "season_auto_complete_interval_days": update.season_auto_complete_interval_days,
            "season_auto_complete_allow_uncached": update.season_auto_complete_allow_uncached,
            "season_auto_complete_shows_per_minute": update.season_auto_complete_shows_per_minute,
            "torbox_requests_per_minute": update.torbox_requests_per_minute,
            "resolver_negative_cache_seconds": update.resolver_negative_cache_seconds,
            "resolver_circuit_breaker_failures": update.resolver_circuit_breaker_failures,
            "resolver_circuit_breaker_window_seconds": update.resolver_circuit_breaker_window_seconds,
            "resolver_circuit_breaker_cooldown_seconds": update.resolver_circuit_breaker_cooldown_seconds,
        }
        if not any(value is not None for value in values.values()):
            return
        application_settings = await self._application_settings()
        if application_settings is None:
            application_settings = ApplicationSettings()
            self._session.add(application_settings)
        for field, value in values.items():
            if value is not None:
                setattr(application_settings, field, value)

    async def _save_provider_secret(self, provider: str, name: str, value: str) -> None:
        box = self._secret_box()
        result = await self._session.execute(
            select(ProviderCredential).where(
                ProviderCredential.provider == provider,
                ProviderCredential.credential_name == name,
            )
        )
        credential = result.scalar_one_or_none()
        if credential is None:
            self._session.add(
                ProviderCredential(
                    provider=provider,
                    credential_name=name,
                    encrypted_value=box.seal(value),
                    secret_hint=public_secret_hint(value),
                )
            )
            return
        credential.encrypted_value = box.seal(value)
        credential.secret_hint = public_secret_hint(value)

    async def _save_resolver_token(self, token: str) -> None:
        token_hash = sha256_hex(token)
        result = await self._session.execute(
            select(ResolverToken).where(ResolverToken.token_hash == token_hash)
        )
        if result.scalar_one_or_none() is None:
            self._session.add(ResolverToken(label="default", token_hash=token_hash))

    async def _ensure_resolver_token(self) -> None:
        if self._settings.resolver_token is not None:
            return
        if await self._provider_secret_exists("resolver", "token"):
            return
        token = secrets.token_urlsafe(GENERATED_RESOLVER_TOKEN_BYTES)
        await self._save_resolver_token(token)
        await self._save_provider_secret("resolver", "token", token)

    async def _provider_secret_exists(self, provider: str, name: str) -> bool:
        result = await self._session.execute(
            select(ProviderCredential.id).where(
                ProviderCredential.provider == provider,
                ProviderCredential.credential_name == name,
            )
        )
        return result.scalar_one_or_none() is not None

    async def _provider_credential(
        self,
        provider: str,
        name: str,
    ) -> ProviderCredential | None:
        result = await self._session.execute(
            select(ProviderCredential).where(
                ProviderCredential.provider == provider,
                ProviderCredential.credential_name == name,
            )
        )
        return result.scalar_one_or_none()

    async def _secret_source(
        self,
        *,
        env_configured: bool,
        provider: str,
        name: str,
    ) -> SettingSource | None:
        if env_configured:
            return "environment"
        if await self._provider_secret_exists(provider, name):
            return "database"
        return None

    async def _resolver_source(self, *, env_configured: bool) -> SettingSource | None:
        if env_configured:
            return "environment"
        if await self._provider_secret_exists("resolver", "token"):
            return "database"
        return None

    def _secret_box(self) -> SecretBox:
        if self._settings.app_secret_key is None:
            msg = "STRMLINE_APP_SECRET_KEY is required to store provider secrets."
            raise RuntimeError(msg)
        return SecretBox(self._settings.app_secret_key.get_secret_value())

    def _env_provider_secret(self, provider: ProviderName) -> str | None:
        if provider == "torbox" and self._settings.torbox_api_key is not None:
            return self._settings.torbox_api_key.get_secret_value()
        if provider == "tmdb" and self._settings.tmdb_api_key is not None:
            return self._settings.tmdb_api_key.get_secret_value()
        return None

    async def aiostreams_base_url_value(self) -> str | None:
        if self._settings.aiostreams_base_url is not None:
            return self._settings.aiostreams_base_url.get_secret_value()
        credential = await self._provider_credential("aiostreams", "base_url")
        if credential is None:
            return None
        return self._secret_box().open(credential.encrypted_value)


def _database_value[SettingValue: (bool, int)](
    settings: ApplicationSettings | None,
    field: str,
    *,
    default: SettingValue,
) -> SettingValue:
    if settings is None:
        return default
    value = getattr(settings, field)
    return value if isinstance(value, type(default)) else default


def _env_or_db[SettingValue: (bool, int)](
    env_value: SettingValue | None,
    settings: ApplicationSettings | None,
    field: str,
    *,
    default: SettingValue,
) -> SettingValue:
    if env_value is not None:
        return env_value
    return _database_value(settings, field, default=default)


def _database_playback_mode(settings: ApplicationSettings | None) -> PlaybackMode:
    if settings is not None and settings.playback_mode in ("resolver", "direct"):
        return settings.playback_mode
    return DEFAULT_PLAYBACK_MODE


def _plain_setting_source(
    *,
    env_configured: bool,
    database_configured: bool,
) -> SettingSource | None:
    if env_configured:
        return "environment"
    if database_configured:
        return "database"
    return None


def public_secret_hint(value: str) -> str:
    if len(value) < SECRET_HINT_SUFFIX_LENGTH:
        return "****"
    return f"****{value[-SECRET_HINT_SUFFIX_LENGTH:]}"


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
