from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import AppSetting, ProviderCredential, ResolverToken
from app.security.secrets import SecretBox

SECRET_HINT_SUFFIX_LENGTH = 4
DEFAULT_SYNC_INTERVAL_MINUTES = 360
DEFAULT_PLAYBACK_MODE = "resolver"

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
    base_url_source: SettingSource | None = None
    library_root_source: SettingSource | None = None
    torbox_source: SettingSource | None = None
    tmdb_source: SettingSource | None = None
    resolver_source: SettingSource | None = None


@dataclass(frozen=True, slots=True)
class AppSettingsUpdate:
    base_url: str | None = None
    movies_enabled: bool | None = None
    shows_enabled: bool | None = None
    anime_enabled: bool | None = None
    playback_mode: PlaybackMode | None = None
    sync_interval_minutes: int | None = None
    torbox_api_key: str | None = None
    tmdb_api_key: str | None = None
    resolver_token: str | None = None


class AppSettingsRepository:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def snapshot_with_env(self) -> SettingsSnapshot:
        rows = await self._app_settings()
        database_base_url = _setting_value(rows, "base_url")
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
        return SettingsSnapshot(
            base_url=self._settings.base_url or database_base_url,
            library_root=str(self._settings.library_root),
            movies_enabled=_setting_bool(rows, "movies_enabled", default=True),
            shows_enabled=_setting_bool(rows, "shows_enabled", default=True),
            anime_enabled=_setting_bool(rows, "anime_enabled", default=True),
            playback_mode=(
                self._settings.playback_mode
                if self._settings.playback_mode is not None
                else _setting_playback_mode(rows, "playback_mode")
            ),
            sync_interval_minutes=self._settings.sync_interval_minutes
            if self._settings.sync_interval_minutes is not None
            else _setting_int(
                rows,
                "sync_interval_minutes",
                default=DEFAULT_SYNC_INTERVAL_MINUTES,
            ),
            torbox_configured=torbox_source is not None,
            tmdb_configured=tmdb_source is not None,
            resolver_configured=resolver_source is not None,
            base_url_source=_plain_setting_source(
                env_configured=self._settings.base_url is not None,
                database_configured=database_base_url is not None,
            ),
            library_root_source="environment",
            torbox_source=torbox_source,
            tmdb_source=tmdb_source,
            resolver_source=resolver_source,
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
        await self._session.commit()
        return await self.snapshot_with_env()

    async def clear_saved_setup(self) -> SettingsSnapshot:
        _ = await self._session.execute(
            delete(AppSetting).where(
                AppSetting.key.in_(
                    (
                        "anime_enabled",
                        "base_url",
                        "library_root",
                        "movies_enabled",
                        "playback_mode",
                        "pgid",
                        "puid",
                        "shows_enabled",
                        "sync_interval_minutes",
                    )
                )
            )
        )
        _ = await self._session.execute(
            delete(ProviderCredential).where(
                ProviderCredential.provider.in_(("resolver", "torbox", "tmdb")),
                ProviderCredential.credential_name == "api_key",
            )
        )
        _ = await self._session.execute(
            delete(ProviderCredential).where(
                ProviderCredential.provider == "resolver",
                ProviderCredential.credential_name == "token",
            )
        )
        _ = await self._session.execute(delete(ResolverToken))
        await self._session.commit()
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

    async def _app_settings(self) -> dict[str, AppSetting]:
        result = await self._session.execute(select(AppSetting))
        return {setting.key: setting for setting in result.scalars()}

    async def _save_public_settings(self, update: AppSettingsUpdate) -> None:
        public_settings: tuple[tuple[str, bool | int | str | None], ...] = (
            ("base_url", update.base_url),
            ("movies_enabled", update.movies_enabled),
            ("shows_enabled", update.shows_enabled),
            ("anime_enabled", update.anime_enabled),
            ("playback_mode", update.playback_mode),
            ("sync_interval_minutes", update.sync_interval_minutes),
        )
        for key, value in public_settings:
            if value is not None:
                await self._save_setting(key, value=value)

    async def _save_setting(self, key: str, *, value: bool | int | str) -> None:
        _ = await self._session.merge(
            AppSetting(key=key, value={"value": value}, is_secret=False),
        )

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


def _setting_value(rows: dict[str, AppSetting], key: str) -> str | None:
    setting = rows.get(key)
    if setting is None or setting.value is None:
        return None
    raw_value = setting.value.get("value")
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value
    return None


def _setting_bool(rows: dict[str, AppSetting], key: str, *, default: bool) -> bool:
    setting = rows.get(key)
    if setting is None or setting.value is None:
        return default
    raw_value = setting.value.get("value")
    if isinstance(raw_value, bool):
        return raw_value
    return default


def _setting_int(rows: dict[str, AppSetting], key: str, *, default: int) -> int:
    setting = rows.get(key)
    if setting is None or setting.value is None:
        return default
    raw_value = setting.value.get("value")
    if isinstance(raw_value, int):
        return raw_value
    return default


def _setting_playback_mode(rows: dict[str, AppSetting], key: str) -> PlaybackMode:
    setting = rows.get(key)
    if setting is None or setting.value is None:
        return DEFAULT_PLAYBACK_MODE
    raw_value = setting.value.get("value")
    if raw_value in ("resolver", "direct"):
        return raw_value
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
