from app.db.base import Base
from app.db.models import (
    AniListCacheEntry,
    AppSetting,
    GeneratedFile,
    LibraryEntry,
    LibraryExclusion,
    MediaItem,
    PlaybackAttempt,
    ProviderCredential,
    ResolverToken,
    StreamSelection,
    SyncError,
    SyncRun,
    TmdbCacheEntry,
    TorBoxItem,
)


def test_initial_schema_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "app_settings",
        "anilist_cache_entries",
        "generated_files",
        "library_entries",
        "library_exclusions",
        "media_items",
        "playback_attempts",
        "provider_credentials",
        "resolver_tokens",
        "stream_selections",
        "sync_errors",
        "sync_runs",
        "tmdb_cache_entries",
        "torbox_items",
    }


def test_provider_credentials_store_encrypted_secret_not_plain_value() -> None:
    columns = set(ProviderCredential.__table__.columns.keys())

    assert "encrypted_value" in columns
    assert "value" not in columns
    assert "api_key" not in columns


def test_resolver_tokens_store_hash_not_plain_token() -> None:
    columns = set(ResolverToken.__table__.columns.keys())

    assert "token_hash" in columns
    assert "token" not in columns


def test_sync_and_playback_tables_do_not_store_final_media_urls() -> None:
    for model in (
        LibraryEntry,
        PlaybackAttempt,
        SyncError,
        SyncRun,
        GeneratedFile,
        TorBoxItem,
        StreamSelection,
        LibraryExclusion,
    ):
        column_names = set(model.__table__.columns.keys())
        assert "target_url" not in column_names
        assert "final_url" not in column_names


def test_sync_errors_can_be_dismissed() -> None:
    columns = set(SyncError.__table__.columns.keys())

    assert "dismissed_at" in columns


def test_core_models_have_expected_primary_keys() -> None:
    assert {column.name for column in AppSetting.__table__.primary_key} == {"key"}
    assert {column.name for column in MediaItem.__table__.primary_key} == {"id"}
    assert {column.name for column in LibraryEntry.__table__.primary_key} == {"id"}


def test_tmdb_cache_entries_do_not_store_api_keys() -> None:
    columns = set(TmdbCacheEntry.__table__.columns.keys())

    assert "cache_key" in columns
    assert "response_payload" in columns
    assert "api_key" not in columns
    assert "token" not in columns


def test_anilist_cache_entries_store_graphql_payloads_without_tokens() -> None:
    columns = set(AniListCacheEntry.__table__.columns.keys())

    assert "cache_key" in columns
    assert "operation_name" in columns
    assert "response_payload" in columns
    assert "api_key" not in columns
    assert "token" not in columns
