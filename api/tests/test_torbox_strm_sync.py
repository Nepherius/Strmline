from pathlib import Path
from typing import Any

import pytest

from app.library.classification_override import LibraryClassificationOverride
from app.providers.torbox.files import DownloadKind
from app.resolver.manifest import resolve_manifest_target
from app.sync.media_identity import MediaIdentity
from app.sync.torbox_strm import DirectTorBoxStrmSync, ResolverUrlConfig


class FakeTorBoxClient:
    async def list_downloads(
        self, kind: DownloadKind, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        _ = limit
        if kind != "torrents":
            return []
        return [
            {
                "id": 1,
                "name": "Movie.Name.2024",
                "cached": True,
                "files": [
                    {
                        "id": 2,
                        "short_name": "Movie.Name.2024.1080p.mkv",
                        "name": "Movie.Name.2024/Movie.Name.2024.1080p.mkv",
                        "mimetype": "video/x-matroska",
                        "size": 1_000_000_000,
                    },
                ],
            },
        ]


class MultiFileTorBoxClient:
    async def list_downloads(
        self, kind: DownloadKind, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        _ = limit
        if kind != "torrents":
            return []
        return [
            {
                "id": 1,
                "name": "Movies",
                "cached": True,
                "files": [
                    {
                        "id": 2,
                        "short_name": "First.Movie.2024.mkv",
                        "mimetype": "video/x-matroska",
                    },
                    {
                        "id": 3,
                        "short_name": "Second.Movie.2024.mkv",
                        "mimetype": "video/x-matroska",
                    },
                ],
            },
        ]


class DuplicatePathTorBoxClient:
    async def list_downloads(
        self, kind: DownloadKind, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        _ = limit
        if kind != "torrents":
            return []
        return [
            {
                "id": 1,
                "name": "Movie.Name.2024",
                "cached": True,
                "files": [
                    {
                        "id": 2,
                        "short_name": "Movie.Name.2024.1080p.mkv",
                        "mimetype": "video/x-matroska",
                    },
                    {
                        "id": 3,
                        "short_name": "Movie.Name.2024.1080p.mkv",
                        "mimetype": "video/x-matroska",
                    },
                ],
            },
        ]


class AnimeCandidateTorBoxClient:
    async def list_downloads(
        self, kind: DownloadKind, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        _ = limit
        if kind != "torrents":
            return []
        return [
            {
                "id": 1,
                "name": "Frieren",
                "cached": True,
                "files": [
                    {
                        "id": 2,
                        "short_name": "Frieren.S01E01.2023.mkv",
                        "mimetype": "video/x-matroska",
                    },
                ],
            },
        ]


class AnimeMovieCandidateTorBoxClient:
    async def list_downloads(
        self, kind: DownloadKind, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        _ = limit
        if kind != "torrents":
            return []
        return [
            {
                "id": 1,
                "name": "Spirited.Away.2001",
                "cached": True,
                "files": [
                    {
                        "id": 2,
                        "short_name": "Spirited.Away.2001.1080p.mkv",
                        "mimetype": "video/x-matroska",
                    },
                ],
            },
        ]


class AmbiguousShowTorBoxClient:
    async def list_downloads(
        self, kind: DownloadKind, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        _ = limit
        if kind != "torrents":
            return []
        return [
            {
                "id": 1,
                "name": "Vagabond",
                "cached": True,
                "files": [
                    {
                        "id": 2,
                        "short_name": "Vagabond.S01E01.mkv",
                        "mimetype": "video/x-matroska",
                    },
                ],
            },
        ]


class FolderYearAnimeCandidateTorBoxClient:
    async def list_downloads(
        self, kind: DownloadKind, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        _ = limit
        if kind != "torrents":
            return []
        return [
            {
                "id": 1,
                "name": "Frieren (2023)",
                "cached": True,
                "files": [
                    {
                        "id": 2,
                        "short_name": "Frieren.S01E01.1080p.mkv",
                        "mimetype": "video/x-matroska",
                    },
                ],
            },
        ]


class BookwormAnimeCandidateTorBoxClient:
    async def list_downloads(
        self, kind: DownloadKind, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        _ = limit
        if kind != "torrents":
            return []
        return [
            {
                "id": 1,
                "name": "[TTGA] Ascendance of a Bookworm (2022) (Season 3 + Specials)",
                "cached": True,
                "files": [
                    {
                        "id": 2,
                        "short_name": "01 - A World With No Books.mkv",
                        "mimetype": "video/x-matroska",
                    },
                ],
            },
        ]


class SxxFolderAnimeCandidateTorBoxClient:
    async def list_downloads(
        self, kind: DownloadKind, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        _ = limit
        if kind != "torrents":
            return []
        return [
            {
                "id": 8,
                "name": (
                    "[sam] Kaijuu 8-gou - S01 (WEB 1080p HEVC x265 10-bit EAC-3) [Dual-Audio]"
                ),
                "cached": True,
                "files": [
                    {
                        "id": 1,
                        "short_name": "Kaijuu 8-gou - 01 [WEB 1080p HEVC x265].mkv",
                        "mimetype": "video/x-matroska",
                    },
                    {
                        "id": 3,
                        "short_name": "Kaijuu 8-gou - 03v2 [WEB 1080p HEVC x265].mkv",
                        "mimetype": "video/x-matroska",
                    },
                ],
            },
            {
                "id": 9,
                "name": "Kaiju.No.8.S02.1080p.BluRay",
                "cached": True,
                "files": [
                    {
                        "id": 1,
                        "short_name": "Kaiju.No.8.S02E01.1080p.BluRay.mkv",
                        "mimetype": "video/x-matroska",
                    },
                ],
            },
        ]


class FakeAnimeClassifier:
    def __init__(self, *, is_anime: bool) -> None:
        self.is_anime = is_anime
        self.calls: list[tuple[str, int | None]] = []

    async def has_anime_match(self, title: str, *, year: int | None = None) -> bool:
        self.calls.append((title, year))
        return self.is_anime


@pytest.mark.asyncio
async def test_direct_torbox_strm_sync_writes_playable_strm_files(tmp_path: Path) -> None:
    sync = DirectTorBoxStrmSync(
        client=FakeTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
    )

    result = await sync.run(kinds=("torrents",))

    expected_path = tmp_path / "movies" / "Movie Name (2024)" / "Movie Name (2024).strm"
    assert result.scanned_files == 1
    assert result.written_files == 1
    assert result.skipped_files == 0
    assert result.written_paths == (expected_path.resolve(strict=False),)
    assert result.synced_files[0].path == expected_path.resolve(strict=False)
    assert result.synced_files[0].title == "Movie Name"
    assert result.synced_files[0].category == "movies"
    assert result.synced_files[0].provider == "torrents"
    assert result.synced_files[0].provider_item_id == "1"
    assert result.synced_files[0].provider_file_id == "2"
    assert expected_path.read_text(encoding="utf-8") == (
        "https://api.torbox.app/v1/api/torrents/requestdl?"
        "token=test-token&torrent_id=1&file_id=2&redirect=true\n"
    )


@pytest.mark.asyncio
async def test_direct_torbox_strm_sync_can_limit_written_files(tmp_path: Path) -> None:
    sync = DirectTorBoxStrmSync(
        client=MultiFileTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
    )

    result = await sync.run(kinds=("torrents",), max_files=1)

    assert result.scanned_files == 1
    assert result.written_files == 1
    assert len(result.written_paths) == 1


@pytest.mark.asyncio
async def test_direct_torbox_strm_sync_counts_unique_output_paths(tmp_path: Path) -> None:
    sync = DirectTorBoxStrmSync(
        client=DuplicatePathTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
    )

    result = await sync.run(kinds=("torrents",))

    assert result.scanned_files == 2
    assert result.written_files == 1
    assert len(result.written_paths) == 2


@pytest.mark.asyncio
async def test_torbox_strm_sync_writes_resolver_urls_and_manifest(tmp_path: Path) -> None:
    resolver_token = "resolver-secret"  # noqa: S105
    sync = DirectTorBoxStrmSync(
        client=FakeTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
        resolver=ResolverUrlConfig(base_url="http://strmline:8080", token=resolver_token),
    )

    result = await sync.run(kinds=("torrents",))

    expected_path = tmp_path / "movies" / "Movie Name (2024)" / "Movie Name (2024).strm"
    strm_content = expected_path.read_text(encoding="utf-8")
    assert result.manifest_path == tmp_path / ".strmline" / "resolver_manifest.json"
    assert strm_content.startswith("http://strmline:8080/play/")
    assert f"token={resolver_token}" in strm_content
    entry_id = strm_content.split("/play/", maxsplit=1)[1].split("?", maxsplit=1)[0]
    assert resolve_manifest_target(tmp_path, entry_id) == (
        "https://api.torbox.app/v1/api/torrents/requestdl?"
        "token=test-token&torrent_id=1&file_id=2&redirect=true"
    )


@pytest.mark.asyncio
async def test_torbox_strm_sync_uses_anilist_classifier_for_anime(
    tmp_path: Path,
) -> None:
    classifier = FakeAnimeClassifier(is_anime=True)
    sync = DirectTorBoxStrmSync(
        client=AnimeCandidateTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
        anime_classifier=classifier,
    )

    result = await sync.run(kinds=("torrents",))

    expected_path = tmp_path / "anime" / "Frieren" / "Season 01" / "Frieren - S01E01.strm"
    assert result.synced_files[0].category == "anime"
    assert result.written_paths == (expected_path.resolve(strict=False),)
    assert classifier.calls == [("Frieren", 2023)]


@pytest.mark.asyncio
async def test_torbox_strm_sync_keeps_show_when_anilist_does_not_confirm(
    tmp_path: Path,
) -> None:
    classifier = FakeAnimeClassifier(is_anime=False)
    sync = DirectTorBoxStrmSync(
        client=AnimeCandidateTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
        anime_classifier=classifier,
    )

    result = await sync.run(kinds=("torrents",))

    expected_path = tmp_path / "shows" / "Frieren" / "Season 01" / "Frieren - S01E01.strm"
    assert result.synced_files[0].category == "shows"
    assert result.written_paths == (expected_path.resolve(strict=False),)


@pytest.mark.asyncio
async def test_torbox_strm_sync_applies_manual_classification_override(
    tmp_path: Path,
) -> None:
    sync = DirectTorBoxStrmSync(
        client=AnimeCandidateTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
        classification_overrides=(
            LibraryClassificationOverride(
                source_category="shows",
                source_prefix="shows/Frieren",
                title="Frieren",
                target_category="anime",
            ),
        ),
    )

    result = await sync.run(kinds=("torrents",))

    expected_path = tmp_path / "anime" / "Frieren" / "Season 01" / "Frieren - S01E01.strm"
    assert result.synced_files[0].category == "anime"
    assert result.written_paths == (expected_path.resolve(strict=False),)


@pytest.mark.asyncio
async def test_torbox_strm_sync_uses_anilist_classifier_for_anime_movie(
    tmp_path: Path,
) -> None:
    classifier = FakeAnimeClassifier(is_anime=True)
    sync = DirectTorBoxStrmSync(
        client=AnimeMovieCandidateTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
        anime_classifier=classifier,
    )

    result = await sync.run(kinds=("torrents",))

    expected_path = tmp_path / "anime" / "Spirited Away (2001)" / "Spirited Away (2001).strm"
    assert result.synced_files[0].category == "anime"
    assert result.synced_files[0].season_number is None
    assert result.synced_files[0].episode_number is None
    assert result.written_paths == (expected_path.resolve(strict=False),)
    assert classifier.calls == [("Spirited Away", 2001)]


@pytest.mark.asyncio
async def test_torbox_strm_sync_keeps_non_anime_show_when_anilist_rejects(
    tmp_path: Path,
) -> None:
    classifier = FakeAnimeClassifier(is_anime=False)
    sync = DirectTorBoxStrmSync(
        client=AmbiguousShowTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
        anime_classifier=classifier,
    )

    result = await sync.run(kinds=("torrents",))

    expected_path = tmp_path / "shows" / "Vagabond" / "Season 01" / "Vagabond - S01E01.strm"
    assert result.synced_files[0].category == "shows"
    assert result.written_paths == (expected_path.resolve(strict=False),)
    assert classifier.calls == [("Vagabond", None)]


@pytest.mark.asyncio
async def test_torbox_strm_sync_uses_pack_folder_title_for_bracketed_anime_release(
    tmp_path: Path,
) -> None:
    classifier = FakeAnimeClassifier(is_anime=True)
    sync = DirectTorBoxStrmSync(
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
async def test_torbox_strm_sync_uses_sxx_pack_context_for_numbered_anime_files(
    tmp_path: Path,
) -> None:
    classifier = FakeAnimeClassifier(is_anime=True)
    sync = DirectTorBoxStrmSync(
        client=SxxFolderAnimeCandidateTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
        anime_classifier=classifier,
        selected_media_by_torrent_id={
            torrent_id: MediaIdentity(
                tmdb_id="207468",
                title="Kaiju No. 8",
                year=2024,
                media_type="tv",
                poster_path="/kaiju.jpg",
            )
            for torrent_id in ("8", "9")
        },
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
    assert classifier.calls == [
        ("Kaiju No. 8", 2024),
        ("Kaiju No. 8", 2024),
        ("Kaiju No. 8", 2024),
    ]


@pytest.mark.asyncio
async def test_torbox_strm_sync_uses_folder_year_for_anime_classification(
    tmp_path: Path,
) -> None:
    classifier = FakeAnimeClassifier(is_anime=True)
    sync = DirectTorBoxStrmSync(
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
async def test_torbox_strm_sync_removes_stale_strm_files_after_full_sync(
    tmp_path: Path,
) -> None:
    stale_path = tmp_path / "movies" / "Vagabond S01 E01 (2019)" / "Vagabond S01 E01 (2019).strm"
    stale_path.parent.mkdir(parents=True)
    _ = stale_path.write_text("https://old.example/video\n", encoding="utf-8")
    sync = DirectTorBoxStrmSync(
        client=AmbiguousShowTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
    )

    result = await sync.run(kinds=("torrents",))

    expected_path = tmp_path / "shows" / "Vagabond" / "Season 01" / "Vagabond - S01E01.strm"
    assert stale_path.exists() is False
    assert result.written_paths == (expected_path.resolve(strict=False),)


@pytest.mark.asyncio
async def test_torbox_strm_sync_keeps_permanent_virtual_library_paths(
    tmp_path: Path,
) -> None:
    virtual_path = tmp_path / "movies" / "Saved Movie (2024)" / "Saved Movie (2024).strm"
    virtual_path.parent.mkdir(parents=True)
    _ = virtual_path.write_text("http://strmline/play/saved\n", encoding="utf-8")
    sync = DirectTorBoxStrmSync(
        client=AmbiguousShowTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
        preserved_paths={virtual_path},
    )

    _ = await sync.run(kinds=("torrents",))

    assert virtual_path.exists() is True


@pytest.mark.asyncio
async def test_torbox_strm_sync_captures_hash_for_imported_torrent(tmp_path: Path) -> None:
    sync = DirectTorBoxStrmSync(
        client=HashedTorrentClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
    )

    result = await sync.run(kinds=("torrents",))

    assert result.synced_files[0].info_hash == "abc123"


class HashedTorrentClient:
    async def list_downloads(self, kind: str, *, limit: int = 1000) -> list[dict[str, object]]:
        _ = kind
        _ = limit
        return [
            {
                "id": 91,
                "hash": "ABC123",
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
