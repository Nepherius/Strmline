from __future__ import annotations

from app.api.file_manifests import (
    LibraryManifestFile,
    library_manifest_response,
    torbox_manifest_response,
)
from app.providers.torbox.manifests import TorBoxManifestFile, TorBoxTorrentManifest


def _library_file(
    entry_id: int,
    name: str,
    *,
    season: int | None,
    episode: int | None,
    source: str,
) -> LibraryManifestFile:
    return LibraryManifestFile(
        library_entry_id=entry_id,
        source_key=source,
        name=name,
        path=f"Show/{name}",
        size=entry_id * 1000,
        mime_type="video/x-matroska",
        season=season,
        episode=episode,
    )


def test_library_manifest_collapses_multiple_versions_of_an_episode() -> None:
    response = library_manifest_response(
        (
            _library_file(
                1,
                "Show.S01E01.1080p.mkv",
                season=1,
                episode=1,
                source="torrents:10",
            ),
            _library_file(
                2,
                "Show.S01E01.2160p.mkv",
                season=1,
                episode=1,
                source="torrents:11",
            ),
            _library_file(
                3,
                "Show.S01E02.1080p.mkv",
                season=1,
                episode=2,
                source="torrents:10",
            ),
        ),
        collapse_episode_versions=True,
    )

    assert response.available is True
    assert response.total_files == 3
    assert response.displayed_files == 2
    assert response.source_count == 2
    assert [(file.episode, file.version_count) for file in response.files] == [(1, 2), (2, 1)]


def test_library_manifest_keeps_movie_versions_separate() -> None:
    files = (
        _library_file(1, "Movie.1080p.mkv", season=None, episode=None, source="torrents:10"),
        _library_file(2, "Movie.2160p.mkv", season=None, episode=None, source="torrents:11"),
    )

    response = library_manifest_response(files, collapse_episode_versions=False)

    assert response.total_files == 2
    assert response.displayed_files == 2
    assert [file.name for file in response.files] == ["Movie.1080p.mkv", "Movie.2160p.mkv"]
    assert all(file.version_count == 1 for file in response.files)


def test_torbox_manifest_response_preserves_all_torrent_files() -> None:
    response = torbox_manifest_response(
        TorBoxTorrentManifest(
            info_hash="abc",
            name="Season Pack",
            files=(
                TorBoxManifestFile(
                    external_id="1",
                    name="Show.S01E01.mkv",
                    path="Season 01/Show.S01E01.mkv",
                    size=100,
                    mime_type="video/x-matroska",
                ),
                TorBoxManifestFile(
                    external_id="2",
                    name="Show.S01E01.srt",
                    path="Season 01/Show.S01E01.srt",
                    size=10,
                    mime_type="application/x-subrip",
                ),
            ),
        )
    )

    assert response.total_files == 2
    assert [file.name for file in response.files] == ["Show.S01E01.mkv", "Show.S01E01.srt"]
