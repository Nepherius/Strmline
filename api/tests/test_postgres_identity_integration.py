from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.models import GeneratedFile, LibraryEntry, MediaItem, SourceMediaBinding, SyncRun
from app.db.repositories.media_identity import (
    MediaIdentityRepository,
    MediaIdentityWrite,
    SourceBindingWrite,
)
from app.db.repositories.sync_coordination import SyncCoordinationRepository
from app.db.repositories.sync_runs import SyncRunRepository
from app.db.repositories.sync_state import SyncLibraryStateRepository
from app.domain.media_identity import ContentKind, IdentityAuthority, ProviderMediaKind
from app.sync.torbox_strm import SyncedStrmFile, TorBoxStrmSyncResult

TEST_DATABASE_URL = os.getenv("STRMLINE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="Set STRMLINE_TEST_DATABASE_URL to run PostgreSQL integration tests.",
)


def _write(
    external_id: str,
    *,
    title: str,
    content_kind: ContentKind = ContentKind.SERIES,
    category: str = "anime",
    provider_kind: ProviderMediaKind = ProviderMediaKind.TV,
    authority: IdentityAuthority = IdentityAuthority.SEARCH_CONFIRMED,
) -> MediaIdentityWrite:
    if category not in {"movies", "shows", "anime"}:
        raise ValueError("Invalid test category.")
    return MediaIdentityWrite(
        content_kind=content_kind,
        library_category=category,  # pyright: ignore[reportArgumentType]
        title=title,
        year=2024,
        tmdb_id=external_id,
        provider_media_kind=provider_kind,
        authority=authority,
        confidence=100 if authority.authoritative else 70,
        resolver_version="integration-v1",
    )


@pytest.mark.asyncio
async def test_search_confirmed_identity_and_general_alias_survive_repeat_sync() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            repository = MediaIdentityRepository(session)
            queries = MediaIdentityRepository(session)
            media_item = await repository.ensure_media(_write("900000001", title="Kaiju No. 8"))
            await repository.bind_sources(
                media_item,
                SourceBindingWrite(
                    source_kind="torrents",
                    source_item_id="integration-kaiju",
                    info_hash="ab" * 20,
                    source_title="Kaijuu 8-gou",
                    authority=IdentityAuthority.SEARCH_CONFIRMED,
                    confidence=100,
                    resolver_version="integration-v1",
                ),
            )

            repeated = await repository.ensure_media(
                _write(
                    "900000001",
                    title="Incorrect provider title",
                    authority=IdentityAuthority.PROVIDER_RESOLVED,
                )
            )
            bindings = await queries.source_bindings()
            aliases = await queries.alias_bindings()

            assert repeated.id == media_item.id
            assert (repeated.title, repeated.year, repeated.library_category) == (
                "Kaiju No. 8",
                2024,
                "anime",
            )
            binding = next(row for row in bindings if row.source_item_id == "integration-kaiju")
            assert binding.identity.tmdb_id == "900000001"
            assert binding.identity.authoritative is True
            assert {
                row.normalized_alias
                for row in aliases
                if row.identity.media_item_id == media_item.id
            } == {"kaiju no 8", "kaijuu 8 gou", "incorrect provider title"}
            await session.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_manual_tmdb_correction_survives_repeat_sync() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            repository = MediaIdentityRepository(session)
            queries = MediaIdentityRepository(session)
            media_item = await repository.ensure_media(
                _write(
                    "900000003",
                    title="Ascendance of a Bookworm",
                    authority=IdentityAuthority.PROVIDER_RESOLVED,
                )
            )
            await repository.bind_sources(
                media_item,
                SourceBindingWrite(
                    source_kind="torrents",
                    source_item_id="integration-bookworm",
                    info_hash="cd" * 20,
                    source_title="Ascendance of a Bookworm",
                    authority=IdentityAuthority.PROVIDER_RESOLVED,
                    confidence=70,
                    resolver_version="integration-v1",
                ),
            )
            corrected = await repository.set_manual_tmdb_identity(media_item, "91768")

            repeated = await repository.ensure_media(
                _write(
                    "91768",
                    title="Incorrect provider title",
                    authority=IdentityAuthority.PROVIDER_RESOLVED,
                )
            )
            identity = await queries.tmdb_identity_for_media(corrected.id)
            binding = next(
                row
                for row in await queries.source_bindings()
                if row.source_item_id == "integration-bookworm"
            )

            assert repeated.id == corrected.id
            assert repeated.title == "Ascendance of a Bookworm"
            assert identity is not None
            assert (identity.external_id, identity.authority, identity.authoritative) == (
                "91768",
                IdentityAuthority.MANUAL.value,
                True,
            )
            assert binding.identity.tmdb_id == "91768"
            assert binding.identity.authority == IdentityAuthority.MANUAL.value
            await session.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_overlapping_movie_and_tv_tmdb_numbers_are_distinct_identities() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            repository = MediaIdentityRepository(session)
            movie = await repository.ensure_media(
                _write(
                    "900000002",
                    title="Shared Number Movie",
                    content_kind=ContentKind.MOVIE,
                    category="movies",
                    provider_kind=ProviderMediaKind.MOVIE,
                )
            )
            series = await repository.ensure_media(
                _write("900000002", title="Shared Number Series")
            )

            assert movie.id != series.id
            await session.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_sync_lock_blocks_a_second_connection() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as first, factory() as second:
            first_lock = SyncCoordinationRepository(first)
            second_lock = SyncCoordinationRepository(second)

            assert await first_lock.try_lock() is True
            assert await second_lock.try_lock() is False
            await first_lock.release()
            assert await second_lock.try_lock() is True
            await second_lock.release()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_conflict_lock_serializes_concurrent_identity_inserts() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as first, factory() as second:
            first_item = await MediaIdentityRepository(first).ensure_media(
                _write("900000004", title="Concurrent Identity")
            )
            second_task = asyncio.create_task(
                MediaIdentityRepository(second).ensure_media(
                    _write("900000004", title="Concurrent Identity")
                )
            )
            await asyncio.sleep(0.05)
            assert second_task.done() is False

            await first.commit()
            second_item = await asyncio.wait_for(second_task, timeout=1)
            await second.commit()

            assert second_item.id == first_item.id
            _ = await second.execute(delete(MediaItem).where(MediaItem.id == second_item.id))
            await second.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_repeat_sync_keeps_one_media_and_library_hierarchy(tmp_path: Path) -> None:
    assert TEST_DATABASE_URL is not None
    path = tmp_path / "anime" / "Kaiju No. 8" / "Season 01" / "S01E01.strm"
    path.parent.mkdir(parents=True)
    _ = path.write_text("https://resolver.test/entry\n", encoding="utf-8")
    synced_file = SyncedStrmFile(
        path=path,
        entry_id="integration-repeat-entry",
        category="anime",
        title="Kaiju No. 8",
        year=2024,
        season_number=1,
        episode_number=1,
        provider="torrents",
        provider_item_id="integration-repeat-item",
        provider_file_id="integration-repeat-file",
        provider_item_name="Kaijuu 8-gou",
        provider_file_name="Kaijuu 8-gou - S01E01.mkv",
        provider_file_path="Season 01/Kaijuu 8-gou - S01E01.mkv",
        provider_file_mime_type="video/x-matroska",
        provider_file_size=1_000,
        content_hash="ef" * 32,
        tmdb_id="900000005",
        info_hash="ef" * 20,
        source_title="Kaijuu 8-gou",
        identity_authority=IdentityAuthority.SEARCH_CONFIRMED,
        identity_confidence=100,
        identity_resolver_version="integration-v1",
    )
    result = TorBoxStrmSyncResult(
        scanned_files=1,
        written_files=1,
        skipped_files=0,
        written_paths=(path,),
        synced_files=(synced_file,),
    )
    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            repository = SyncLibraryStateRepository(session)
            _ = await SyncRunRepository(session).record_success(result)
            await repository.persist_result(result, tmp_path)
            await session.commit()
            _ = await SyncRunRepository(session).record_success(result)
            await repository.persist_result(result, tmp_path)
            await session.commit()

            counts: list[int] = []
            for model in (MediaItem, LibraryEntry, GeneratedFile, SourceMediaBinding, SyncRun):
                count = await session.scalar(select(func.count()).select_from(model))
                assert count is not None
                counts.append(count)
            assert tuple(counts) == (1, 1, 1, 2, 2)
            _ = await session.execute(
                text("TRUNCATE TABLE sync_runs, media_items, torbox_items RESTART IDENTITY CASCADE")
            )
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_alembic_migrations_upgrade_and_downgrade_real_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    base_url = make_url(TEST_DATABASE_URL)
    database_name = "strmline_migration_integration"
    admin_url = base_url.set(database="postgres")
    test_url = base_url.set(database=database_name)
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as connection:
        _ = await connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        _ = await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    try:
        monkeypatch.setenv(
            "STRMLINE_DATABASE_URL",
            test_url.render_as_string(hide_password=False),
        )
        get_settings.cache_clear()
        config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
        await asyncio.to_thread(command.upgrade, config, "head")

        engine = create_async_engine(test_url)
        async with engine.connect() as connection:
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            constraints = await connection.scalar(
                text(
                    "SELECT COUNT(*) FROM pg_constraint WHERE conname = 'uq_media_external_identities_provider_kind_id'"
                )
            )
        await engine.dispose()
        assert revision == "20260718_0019"
        assert constraints == 1

        await asyncio.to_thread(command.downgrade, config, "base")
    finally:
        get_settings.cache_clear()
        async with admin_engine.connect() as connection:
            _ = await connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        await admin_engine.dispose()
