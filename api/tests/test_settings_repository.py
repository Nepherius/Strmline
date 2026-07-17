import base64
import hashlib
import hmac
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import ApplicationSettings, ProviderCredential, ResolverToken
from app.db.repositories.settings import (
    AppSettingsRepository,
    AppSettingsUpdate,
    public_secret_hint,
    sha256_hex,
)
from app.security.secrets import SecretBox


class FakeScalars:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def __iter__(self) -> Iterator[object]:
        return iter(self._values)


class FakeResult:
    def __init__(self, scalar: object | None = None, scalars: list[object] | None = None) -> None:
        self._scalar = scalar
        self._scalars = scalars or []

    def scalar_one_or_none(self) -> object | None:
        return self._scalar

    def scalars(self) -> FakeScalars:
        return FakeScalars(self._scalars)


class FakeSession:
    def __init__(self, results: list[FakeResult]) -> None:
        self._results = results
        self.added: list[object] = []
        self.merged: list[object] = []
        self.statements: list[object] = []
        self.committed = False

    async def execute(self, statement: object) -> FakeResult:
        self.statements.append(statement)
        return self._results.pop(0)

    async def merge(self, instance: object) -> object:
        self.merged.append(instance)
        return instance

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def commit(self) -> None:
        self.committed = True

    async def flush(self) -> None:
        return None


def test_secret_box_round_trips_without_storing_plaintext() -> None:
    box = SecretBox("local-test-secret")

    sealed = box.seal("torbox-api-key")

    assert sealed != "torbox-api-key"
    assert sealed.startswith("v2:")
    assert box.open(sealed) == "torbox-api-key"


def test_secret_box_rejects_modified_payload() -> None:
    box = SecretBox("local-test-secret")
    sealed = box.seal("torbox-api-key")

    with pytest.raises(ValueError, match="authentication"):
        _ = box.open(f"{sealed[:-1]}A")


def test_secret_box_reads_legacy_payloads() -> None:
    key = "local-test-secret"
    box = SecretBox(key)

    assert box.open(_legacy_seal(key, "torbox-api-key")) == "torbox-api-key"


def test_settings_reject_placeholder_app_secret_key() -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        _ = Settings(app_secret_key=SecretStr("CHANGE_ME_generate_a_long_random_secret"))


def test_secret_hint_does_not_expose_full_secret() -> None:
    assert public_secret_hint("abcdef123456") == "****3456"
    assert public_secret_hint("abc") == "****"


def test_sha256_hex_is_stable_and_not_plaintext() -> None:
    digest = sha256_hex("resolver-token")

    assert digest == sha256_hex("resolver-token")
    assert digest != "resolver-token"
    assert len(digest) == 64


def _legacy_seal(key: str, value: str) -> str:
    key_bytes = hashlib.sha256(key.encode("utf-8")).digest()
    nonce = b"legacy-secret-v1"
    payload = value.encode("utf-8")
    encrypted = _xor_bytes(payload, _legacy_keystream(key_bytes, nonce, len(payload)))
    mac = hmac.new(key_bytes, nonce + encrypted, hashlib.sha256).digest()
    return f"v1:{base64.urlsafe_b64encode(nonce + mac + encrypted).decode('ascii')}"


def _legacy_keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < length:
        output.extend(hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest())
        counter += 1
    return bytes(output[:length])


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(left_byte ^ right_byte for left_byte, right_byte in zip(left, right, strict=True))


@pytest.mark.asyncio
async def test_settings_repository_saves_public_values_and_secrets() -> None:
    session = FakeSession(
        [
            FakeResult(),  # missing application settings
            FakeResult(),  # missing torbox credential
            FakeResult(),  # missing tmdb credential
            FakeResult(),  # missing resolver hash
            FakeResult(),  # missing resolver token credential
            FakeResult(),  # missing aiostreams base URL credential
            FakeResult(),  # snapshot application settings
            FakeResult(scalar=1),  # torbox configured
            FakeResult(scalar=2),  # tmdb configured
            FakeResult(scalar=3),  # resolver configured
            FakeResult(scalar=4),  # aiostreams configured
        ]
    )
    app_secret = SecretStr("app-secret")
    resolver_secret = "resolver-secret"  # noqa: S105
    repository = AppSettingsRepository(
        cast(AsyncSession, session),
        Settings(app_secret_key=app_secret),
    )

    snapshot = await repository.save(
        AppSettingsUpdate(
            base_url="http://strmline.test",
            movies_enabled=False,
            shows_enabled=True,
            anime_enabled=True,
            playback_mode="direct",
            sync_interval_minutes=120,
            debug_logging=True,
            season_auto_complete_enabled=True,
            season_auto_complete_interval_days=3,
            season_auto_complete_allow_uncached=True,
            season_auto_complete_shows_per_minute=2,
            torbox_api_key="torbox-secret",
            tmdb_api_key="tmdb-secret",
            resolver_token=resolver_secret,
            aiostreams_base_url="https://aio.example/manifest.json",
        )
    )

    assert session.committed is False
    saved_settings = next(item for item in session.added if isinstance(item, ApplicationSettings))
    assert saved_settings.base_url == "http://strmline.test"
    assert saved_settings.movies_enabled is False
    assert saved_settings.playback_mode == "direct"
    assert saved_settings.sync_interval_minutes == 120
    assert saved_settings.debug_logging is True
    assert saved_settings.season_auto_complete_interval_days == 3
    assert saved_settings.season_auto_complete_allow_uncached is True
    assert saved_settings.season_auto_complete_shows_per_minute == 2
    credentials = [item for item in session.added if isinstance(item, ProviderCredential)]
    resolver_tokens = [item for item in session.added if isinstance(item, ResolverToken)]
    assert len(credentials) == 4
    assert all("secret" not in credential.encrypted_value for credential in credentials)
    assert {credential.provider for credential in credentials} == {
        "aiostreams",
        "resolver",
        "tmdb",
        "torbox",
    }
    assert resolver_tokens[0].token_hash == sha256_hex("resolver-secret")
    assert snapshot.movies_enabled is True
    assert snapshot.shows_enabled is True
    assert snapshot.anime_enabled is True
    assert snapshot.torbox_configured is True
    assert snapshot.torbox_source == "database"
    assert snapshot.tmdb_source == "database"
    assert snapshot.resolver_source == "database"
    assert snapshot.aiostreams_configured is True
    assert snapshot.aiostreams_source == "database"


@pytest.mark.asyncio
async def test_settings_repository_generates_resolver_token_when_missing() -> None:
    session = FakeSession(
        [
            FakeResult(),  # missing torbox credential
            FakeResult(scalar=None),  # no saved resolver credential
            FakeResult(),  # missing resolver hash
            FakeResult(),  # missing resolver token credential
            FakeResult(),  # snapshot application settings
            FakeResult(scalar=1),  # torbox configured
            FakeResult(scalar=None),  # tmdb missing
            FakeResult(scalar=3),  # resolver configured
            FakeResult(scalar=None),  # aiostreams missing
        ]
    )
    repository = AppSettingsRepository(
        cast(AsyncSession, session),
        Settings(app_secret_key=SecretStr("app-secret")),
    )

    snapshot = await repository.save(AppSettingsUpdate(torbox_api_key="torbox-secret"))

    credentials = [item for item in session.added if isinstance(item, ProviderCredential)]
    resolver_tokens = [item for item in session.added if isinstance(item, ResolverToken)]
    assert session.committed is False
    assert {credential.provider for credential in credentials} == {"resolver", "torbox"}
    assert len(resolver_tokens) == 1
    assert snapshot.resolver_configured is True
    assert snapshot.resolver_source == "database"


@pytest.mark.asyncio
async def test_settings_repository_reads_database_values_when_env_is_missing() -> None:
    session = FakeSession(
        [
            FakeResult(
                scalar=ApplicationSettings(
                    base_url="http://db.test",
                    movies_enabled=False,
                    shows_enabled=True,
                    anime_enabled=True,
                    playback_mode="direct",
                    sync_interval_minutes=45,
                    debug_logging=True,
                    season_auto_complete_enabled=True,
                    season_auto_complete_interval_days=2,
                    season_auto_complete_allow_uncached=True,
                    season_auto_complete_shows_per_minute=2,
                )
            ),
            FakeResult(scalar=1),
            FakeResult(scalar=None),
            FakeResult(scalar=3),
            FakeResult(scalar=4),
        ]
    )
    repository = AppSettingsRepository(
        cast(AsyncSession, session),
        Settings(),
    )

    snapshot = await repository.snapshot_with_env()

    assert snapshot.base_url == "http://db.test"
    assert snapshot.library_root == "/library"
    assert snapshot.movies_enabled is False
    assert snapshot.shows_enabled is True
    assert snapshot.anime_enabled is True
    assert snapshot.playback_mode == "direct"
    assert snapshot.sync_interval_minutes == 45
    assert snapshot.debug_logging is True
    assert snapshot.season_auto_complete_enabled is True
    assert snapshot.season_auto_complete_interval_days == 2
    assert snapshot.season_auto_complete_allow_uncached is True
    assert snapshot.season_auto_complete_shows_per_minute == 2
    assert snapshot.torbox_configured is True
    assert snapshot.tmdb_configured is False
    assert snapshot.resolver_configured is True
    assert snapshot.aiostreams_configured is True
    assert snapshot.base_url_source == "database"
    assert snapshot.library_root_source == "environment"
    assert snapshot.torbox_source == "database"
    assert snapshot.tmdb_source is None
    assert snapshot.resolver_source == "database"
    assert snapshot.aiostreams_source == "database"


@pytest.mark.asyncio
async def test_settings_repository_reports_resolver_source_from_saved_secret() -> None:
    session = FakeSession(
        [
            FakeResult(),
            FakeResult(scalar=None),
            FakeResult(scalar=None),
            FakeResult(scalar=None),
            FakeResult(scalar=None),
        ]
    )
    repository = AppSettingsRepository(
        cast(AsyncSession, session),
        Settings(),
    )

    snapshot = await repository.snapshot_with_env()

    resolver_statement = str(session.statements[-1])
    assert "provider_credentials" in resolver_statement
    assert "resolver_tokens" not in resolver_statement
    assert snapshot.resolver_configured is False
    assert snapshot.resolver_source is None
    assert snapshot.aiostreams_configured is False
    assert snapshot.aiostreams_source is None


@pytest.mark.asyncio
async def test_settings_repository_reports_environment_sources() -> None:
    session = FakeSession(
        [
            FakeResult(),
        ]
    )
    repository = AppSettingsRepository(
        cast(AsyncSession, session),
        Settings(
            base_url="http://env.test",
            library_root=Path("/env-library"),
            torbox_api_key=SecretStr("torbox"),
            tmdb_api_key=SecretStr("tmdb"),
            resolver_token=SecretStr("resolver"),
            aiostreams_base_url=SecretStr("https://aio.example/manifest.json"),
            playback_mode="direct",
            sync_interval_minutes=180,
        ),
    )

    snapshot = await repository.snapshot_with_env()

    assert snapshot.base_url_source == "environment"
    assert snapshot.library_root_source == "environment"
    assert snapshot.torbox_source == "environment"
    assert snapshot.tmdb_source == "environment"
    assert snapshot.resolver_source == "environment"
    assert snapshot.aiostreams_source == "environment"
    assert snapshot.aiostreams_configured is True
    assert snapshot.playback_mode == "direct"
    assert snapshot.sync_interval_minutes == 180


@pytest.mark.asyncio
async def test_settings_repository_reads_provider_api_key() -> None:
    box = SecretBox("app-secret")
    session = FakeSession(
        [
            FakeResult(
                scalar=ProviderCredential(
                    provider="torbox",
                    credential_name="api_key",
                    encrypted_value=box.seal("torbox-secret"),
                )
            ),
        ]
    )
    repository = AppSettingsRepository(
        cast(AsyncSession, session),
        Settings(app_secret_key=SecretStr("app-secret")),
    )

    assert await repository.provider_api_key("torbox") == "torbox-secret"


@pytest.mark.asyncio
async def test_settings_repository_prefers_environment_provider_api_key() -> None:
    session = FakeSession([])
    repository = AppSettingsRepository(
        cast(AsyncSession, session),
        Settings(torbox_api_key=SecretStr("env-torbox-secret")),
    )

    assert await repository.provider_api_key("torbox") == "env-torbox-secret"


@pytest.mark.asyncio
async def test_settings_repository_reads_saved_resolver_token() -> None:
    box = SecretBox("app-secret")
    session = FakeSession(
        [
            FakeResult(
                scalar=ProviderCredential(
                    provider="resolver",
                    credential_name="token",
                    encrypted_value=box.seal("resolver-secret"),
                )
            ),
        ]
    )
    repository = AppSettingsRepository(
        cast(AsyncSession, session),
        Settings(app_secret_key=SecretStr("app-secret")),
    )

    assert await repository.resolver_token_value() == "resolver-secret"


@pytest.mark.asyncio
async def test_settings_repository_reads_saved_aiostreams_url() -> None:
    box = SecretBox("app-secret")
    session = FakeSession(
        [
            FakeResult(
                scalar=ProviderCredential(
                    provider="aiostreams",
                    credential_name="base_url",
                    encrypted_value=box.seal("https://aio.example/manifest.json"),
                )
            ),
        ]
    )
    repository = AppSettingsRepository(
        cast(AsyncSession, session),
        Settings(app_secret_key=SecretStr("app-secret")),
    )

    assert await repository.aiostreams_base_url_value() == "https://aio.example/manifest.json"


@pytest.mark.asyncio
async def test_settings_repository_prefers_environment_aiostreams_url() -> None:
    session = FakeSession([])
    repository = AppSettingsRepository(
        cast(AsyncSession, session),
        Settings(aiostreams_base_url=SecretStr("https://env-aio.example/manifest.json")),
    )

    assert await repository.aiostreams_base_url_value() == "https://env-aio.example/manifest.json"
