from pathlib import Path

import pytest

from app.domain.media_identity import IdentityAuthority, ResolutionStatus
from app.sync.identity_inputs import IdentityInputs
from app.sync.media_identity import MediaIdentity
from app.sync.torbox_strm import TorBoxStrmSync
from tests.test_torbox_strm_sync import (
    AmbiguousShowTorBoxClient,
    BookwormAnimeCandidateTorBoxClient,
    DuplicatePathTorBoxClient,
    FakeAnimeClassifier,
    FakeTorBoxClient,
    FolderYearAnimeCandidateTorBoxClient,
    SxxFolderAnimeCandidateTorBoxClient,
)


@pytest.mark.asyncio
async def test_unmatched_titles_create_one_diagnostic_per_title(tmp_path: Path) -> None:
    class NoMatchResolver:
        async def resolve(
            self,
            parsed_title: str,
            year: int | None,
            category: str,
        ) -> MediaIdentity:
            _ = category
            return MediaIdentity(
                tmdb_id=None,
                title=parsed_title,
                year=year,
                media_type="movie",
                authority=IdentityAuthority.FALLBACK,
                status=ResolutionStatus.NO_MATCH,
            )

    result = await TorBoxStrmSync(
        client=DuplicatePathTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
        media_identity_resolver=NoMatchResolver(),
    ).run(kinds=("torrents",))

    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].phase == "metadata_match"
    assert result.diagnostics[0].item_ref == "Movie Name"


@pytest.mark.asyncio
async def test_migrated_identity_without_external_id_is_retried_and_can_resolve(
    tmp_path: Path,
) -> None:
    class ResolvedIdentity:
        async def resolve(
            self,
            parsed_title: str,
            year: int | None,
            category: str,
        ) -> MediaIdentity:
            _ = (parsed_title, year, category)
            return MediaIdentity(
                tmdb_id="1234",
                title="Movie Name",
                year=2024,
                media_type="movie",
            )

    result = await TorBoxStrmSync(
        client=FakeTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
        media_identity_resolver=ResolvedIdentity(),
        identity_inputs=IdentityInputs(
            by_torrent_id={},
            by_info_hash={},
            by_alias={
                ("movie", "movie name"): MediaIdentity(
                    tmdb_id=None,
                    title="Movie Name",
                    year=2024,
                    media_type="movie",
                    authority=IdentityAuthority.MIGRATED,
                )
            },
        ),
    ).run(kinds=("torrents",))

    assert result.synced_files[0].tmdb_id == "1234"
    assert result.diagnostics == ()


@pytest.mark.asyncio
async def test_torbox_strm_sync_uses_pack_folder_title_for_bracketed_anime_release(
    tmp_path: Path,
) -> None:
    classifier = FakeAnimeClassifier(is_anime=True)
    sync = TorBoxStrmSync(
        client=BookwormAnimeCandidateTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
        anime_classifier=classifier,
    )

    result = await sync.run(kinds=("torrents",))

    expected_path = (
        tmp_path
        / "anime"
        / "Ascendance of a Bookworm"
        / "Season 03"
        / "Ascendance of a Bookworm - S03E01.strm"
    )
    assert result.synced_files[0].category == "anime"
    assert result.written_paths == (expected_path.resolve(strict=False),)
    assert classifier.calls == [("Ascendance of a Bookworm", 2022)]


@pytest.mark.asyncio
async def test_persisted_classification_is_not_reclassified_during_sync(
    tmp_path: Path,
) -> None:
    classifier = FakeAnimeClassifier(is_anime=True)
    sync = TorBoxStrmSync(
        client=AmbiguousShowTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
        anime_classifier=classifier,
        identity_inputs=IdentityInputs(
            by_torrent_id={
                "1": MediaIdentity(
                    tmdb_id="999001",
                    title="Vagabond",
                    year=2019,
                    media_type="tv",
                    library_category="shows",
                )
            },
            by_info_hash={},
            by_alias={},
        ),
    )

    result = await sync.run(kinds=("torrents",))

    assert result.synced_files[0].category == "shows"
    assert classifier.calls == []


@pytest.mark.asyncio
async def test_torbox_strm_sync_groups_kaiju_alias_and_selected_season_under_one_identity(
    tmp_path: Path,
) -> None:
    classifier = FakeAnimeClassifier(is_anime=True)

    class KaijuAliasResolver:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def resolve(
            self,
            parsed_title: str,
            year: int | None,
            category: str,
        ) -> MediaIdentity:
            _ = (year, category)
            self.calls.append(parsed_title)
            return MediaIdentity(
                tmdb_id="207468",
                title="Kaiju No. 8",
                year=2024,
                media_type="tv",
                poster_path="/kaiju.jpg",
            )

    resolver = KaijuAliasResolver()
    sync = TorBoxStrmSync(
        client=SxxFolderAnimeCandidateTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
        anime_classifier=classifier,
        identity_inputs=IdentityInputs(
            by_torrent_id={
                "9": MediaIdentity(
                    tmdb_id="207468",
                    title="Kaiju No. 8",
                    year=2024,
                    media_type="tv",
                    poster_path="/kaiju.jpg",
                )
            },
            by_info_hash={},
            by_alias={},
        ),
        media_identity_resolver=resolver,
    )

    result = await sync.run(kinds=("torrents",))

    expected_paths = (
        tmp_path / "anime" / "Kaiju No. 8" / "Season 01" / "Kaiju No. 8 - S01E01.strm",
        tmp_path / "anime" / "Kaiju No. 8" / "Season 01" / "Kaiju No. 8 - S01E03.strm",
        tmp_path / "anime" / "Kaiju No. 8" / "Season 02" / "Kaiju No. 8 - S02E01.strm",
    )
    assert [file.category for file in result.synced_files] == ["anime", "anime", "anime"]
    assert {file.title for file in result.synced_files} == {"Kaiju No. 8"}
    assert {file.tmdb_id for file in result.synced_files} == {"207468"}
    assert result.written_paths == tuple(path.resolve(strict=False) for path in expected_paths)
    assert set(resolver.calls) == {"Kaijuu 8 gou"}
    assert classifier.calls == [
        ("Kaijuu 8 gou", None),
        ("Kaijuu 8 gou", None),
        ("Kaiju No. 8", 2024),
    ]


@pytest.mark.asyncio
async def test_torbox_strm_sync_uses_folder_year_for_anime_classification(
    tmp_path: Path,
) -> None:
    classifier = FakeAnimeClassifier(is_anime=True)
    sync = TorBoxStrmSync(
        client=FolderYearAnimeCandidateTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
        anime_classifier=classifier,
    )

    result = await sync.run(kinds=("torrents",))

    expected_path = tmp_path / "anime" / "Frieren" / "Season 01" / "Frieren - S01E01.strm"
    assert result.synced_files[0].category == "anime"
    assert result.synced_files[0].year == 2023
    assert result.written_paths == (expected_path.resolve(strict=False),)
    assert classifier.calls == [("Frieren", 2023)]


@pytest.mark.asyncio
async def test_torbox_strm_sync_defers_stale_deletion_until_database_commit(
    tmp_path: Path,
) -> None:
    stale_path = tmp_path / "movies" / "Vagabond S01 E01 (2019)" / "Vagabond.strm"
    stale_path.parent.mkdir(parents=True)
    _ = stale_path.write_text("https://old.example/video\n", encoding="utf-8")
    sync = TorBoxStrmSync(
        client=AmbiguousShowTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
    )

    result = await sync.run(kinds=("torrents",))

    expected_path = tmp_path / "shows" / "Vagabond" / "Season 01" / "Vagabond - S01E01.strm"
    assert stale_path.exists() is True
    assert result.written_paths == (expected_path.resolve(strict=False),)


@pytest.mark.asyncio
async def test_torbox_strm_sync_captures_hash_for_imported_torrent(tmp_path: Path) -> None:
    sync = TorBoxStrmSync(
        client=HashedTorrentClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
    )

    result = await sync.run(kinds=("torrents",))

    assert result.synced_files[0].info_hash == "ab" * 20


class HashedTorrentClient:
    async def list_downloads(self, kind: str, *, limit: int = 1000) -> list[dict[str, object]]:
        _ = kind
        _ = limit
        return [
            {
                "id": 91,
                "hash": "AB" * 20,
                "cached": True,
                "name": "Imported Movie",
                "files": [
                    {
                        "id": 7,
                        "short_name": "Imported.Movie.2024.mkv",
                        "name": "Imported.Movie.2024.mkv",
                        "mimetype": "video/x-matroska",
                        "size": 1_000,
                    }
                ],
            }
        ]
