from collections.abc import Iterator
from typing import cast

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import AppSetting, ProviderCredential, ResolverToken
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
        self.committed = False

    async def execute(self, statement: object) -> FakeResult:
        _ = statement
        return self._results.pop(0)

    async def merge(self, instance: object) -> object:
        self.merged.append(instance)
        return instance

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def commit(self) -> None:
        self.committed = True


def test_secret_box_round_trips_without_storing_plaintext() -> None:
    box = SecretBox("local-test-secret")

    sealed = box.seal("torbox-api-key")

    assert sealed != "torbox-api-key"
    assert box.open(sealed) == "torbox-api-key"


def test_secret_box_rejects_modified_payload() -> None:
    box = SecretBox("local-test-secret")
    sealed = box.seal("torbox-api-key")

    with pytest.raises(ValueError, match="authentication"):
        _ = box.open(f"{sealed[:-1]}A")


def test_secret_hint_does_not_expose_full_secret() -> None:
    assert public_secret_hint("abcdef123456") == "****3456"
    assert public_secret_hint("abc") == "****"


def test_sha256_hex_is_stable_and_not_plaintext() -> None:
    digest = sha256_hex("resolver-token")

    assert digest == sha256_hex("resolver-token")
    assert digest != "resolver-token"
    assert len(digest) == 64


@pytest.mark.asyncio
async def test_settings_repository_saves_public_values_and_secrets() -> None:
    session = FakeSession(
        [
            FakeResult(),  # missing torbox credential
            FakeResult(),  # missing tmdb credential
            FakeResult(),  # missing resolver hash
            FakeResult(scalars=[]),  # snapshot app settings
            FakeResult(scalar=1),  # torbox configured
            FakeResult(scalar=2),  # tmdb configured
            FakeResult(scalar=3),  # resolver configured
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
            library_root="/library",
            torbox_api_key="torbox-secret",
            tmdb_api_key="tmdb-secret",
            resolver_token=resolver_secret,
        )
    )

    assert session.committed is True
    merged_settings = [item for item in session.merged if isinstance(item, AppSetting)]
    assert [setting.key for setting in merged_settings] == ["base_url", "library_root"]
    credentials = [item for item in session.added if isinstance(item, ProviderCredential)]
    resolver_tokens = [item for item in session.added if isinstance(item, ResolverToken)]
    assert len(credentials) == 2
    assert all("secret" not in credential.encrypted_value for credential in credentials)
    assert resolver_tokens[0].token_hash == sha256_hex("resolver-secret")
    assert snapshot.torbox_configured is True


@pytest.mark.asyncio
async def test_settings_repository_reads_database_values_when_env_is_missing() -> None:
    session = FakeSession(
        [
            FakeResult(
                scalars=[
                    AppSetting(key="base_url", value={"value": "http://db.test"}),
                    AppSetting(key="library_root", value={"value": "/library"}),
                ]
            ),
            FakeResult(scalar=1),
            FakeResult(scalar=None),
            FakeResult(scalar=3),
        ]
    )
    repository = AppSettingsRepository(
        cast(AsyncSession, session),
        Settings(),
    )

    snapshot = await repository.snapshot_with_env()

    assert snapshot.base_url == "http://db.test"
    assert snapshot.library_root == "/library"
    assert snapshot.torbox_configured is True
    assert snapshot.tmdb_configured is False
    assert snapshot.resolver_configured is True
