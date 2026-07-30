from __future__ import annotations

from app.providers.torbox.manifests import (
    torrent_manifest_from_cached_payload,
    torrent_manifest_from_download,
)


def test_cached_torrent_manifest_accepts_case_insensitive_hash_and_file_shapes() -> None:
    upper_hash = "A" * 40
    lower_hash = upper_hash.casefold()
    manifest = torrent_manifest_from_cached_payload(
        {
            "data": {
                upper_hash: {
                    "name": "Season Pack",
                    "files": [
                        {
                            "id": 2,
                            "name": "Season 01/Show.S01E02.mkv",
                            "size": 200,
                            "mimetype": "video/x-matroska",
                        },
                        {
                            "id": 1,
                            "filename": "Show.S01E01.mkv",
                            "size": 100,
                        },
                    ],
                }
            }
        },
        lower_hash,
    )

    assert manifest is not None
    assert manifest.name == "Season Pack"
    assert [file.name for file in manifest.files] == [
        "Show.S01E01.mkv",
        "Show.S01E02.mkv",
    ]
    assert manifest.files[1].path == "Season 01/Show.S01E02.mkv"


def test_cached_torrent_manifest_returns_none_without_files() -> None:
    info_hash = "a" * 40
    manifest = torrent_manifest_from_cached_payload(
        {"data": {info_hash: {"name": "Cached but empty"}}},
        info_hash,
    )

    assert manifest is None


def test_download_manifest_uses_live_torbox_item_files() -> None:
    manifest = torrent_manifest_from_download(
        {
            "name": "Movie",
            "files": [
                {
                    "id": "7",
                    "short_name": "Movie.mkv",
                    "name": "Movie/Movie.mkv",
                    "size": 123,
                }
            ],
        },
        None,
    )

    assert manifest is not None
    assert manifest.info_hash == "unknown"
    assert manifest.files[0].external_id == "7"
    assert manifest.files[0].name == "Movie.mkv"
