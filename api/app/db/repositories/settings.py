from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import AppSetting, ProviderCredential, ResolverToken
from app.security.secrets import SecretBox

SECRET_HINT_SUFFIX_LENGTH = 4


@dataclass(frozen=True, slots=True)
class SettingsSnapshot:
    base_url: str | None
    library_root: str | None
    torbox_configured: bool
    tmdb_configured: bool
    resolver_configured: bool


@dataclass(frozen=True, slots=True)
class AppSettingsUpdate:
    base_url: str | None = None
    library_root: str | None = None
    torbox_api_key: str | None = None
    tmdb_api_key: str | None = None
    resolver_token: str | None = None


class AppSettingsRepository:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def snapshot_with_env(self) -> SettingsSnapshot:
        rows = await self._app_settings()
        return SettingsSnapshot(
            base_url=self._settings.base_url or _setting_value(rows, "base_url"),
            library_root=(
                str(self._settings.library_root)
                if self._settings.library_root is not None
                else _setting_value(rows, "library_root")
            ),
            torbox_configured=(
                self._settings.torbox_api_key is not None
                or await self._provider_secret_exists("torbox", "api_key")
            ),
            tmdb_configured=(
                self._settings.tmdb_api_key is not None
                or await self._provider_secret_exists("tmdb", "api_key")
            ),
            resolver_configured=(
                self._settings.resolver_token is not None
                or await self._active_resolver_token_exists()
            ),
        )

    async def save(self, update: AppSettingsUpdate) -> SettingsSnapshot:
        if update.base_url is not None:
            await self._save_setting("base_url", update.base_url)
        if update.library_root is not None:
            await self._save_setting("library_root", update.library_root)
        if update.torbox_api_key is not None:
            await self._save_provider_secret("torbox", "api_key", update.torbox_api_key)
        if update.tmdb_api_key is not None:
            await self._save_provider_secret("tmdb", "api_key", update.tmdb_api_key)
        if update.resolver_token is not None:
            await self._save_resolver_token(update.resolver_token)
        await self._session.commit()
        return await self.snapshot_with_env()

    async def _app_settings(self) -> dict[str, AppSetting]:
        result = await self._session.execute(select(AppSetting))
        return {setting.key: setting for setting in result.scalars()}

    async def _save_setting(self, key: str, value: str) -> None:
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

    async def _active_resolver_token_exists(self) -> bool:
        result = await self._session.execute(
            select(ResolverToken.id).where(ResolverToken.revoked_at.is_(None))
        )
        return result.scalar_one_or_none() is not None

    def _secret_box(self) -> SecretBox:
        if self._settings.app_secret_key is None:
            msg = "STRMLINE_APP_SECRET_KEY is required to store provider secrets."
            raise RuntimeError(msg)
        return SecretBox(self._settings.app_secret_key.get_secret_value())


def _setting_value(rows: dict[str, AppSetting], key: str) -> str | None:
    setting = rows.get(key)
    if setting is None or setting.value is None:
        return None
    raw_value = setting.value.get("value")
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value
    return None


def public_secret_hint(value: str) -> str:
    if len(value) < SECRET_HINT_SUFFIX_LENGTH:
        return "****"
    return f"****{value[-SECRET_HINT_SUFFIX_LENGTH:]}"


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
