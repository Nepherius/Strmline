from pathlib import Path

import pytest

from app.providers.torbox.files import TorBoxFile
from app.resolver.manifest import (
    ResolverManifestEntry,
    resolve_manifest_target,
    resolver_entry_id,
    resolver_playback_url,
    write_manifest_entries,
)


def test_resolver_entry_id_is_stable() -> None:
    torbox_file = TorBoxFile(
        kind="torrents",
        item_id="10",
        file_id="20",
        folder_name="Movie",
        file_name="Movie.2024.mkv",
        path="Movie.2024.mkv",
        mime_type="video/x-matroska",
        size=100,
    )

    assert resolver_entry_id(torbox_file) == resolver_entry_id(torbox_file)
    assert len(resolver_entry_id(torbox_file)) == 24


def test_resolver_playback_url_uses_local_base_and_token() -> None:
    assert (
        resolver_playback_url("http://strmline:8080/", "secret", "entry-id")
        == "http://strmline:8080/play/entry-id?token=secret"
    )


def test_write_manifest_entries_merges_existing_entries(tmp_path: Path) -> None:
    _ = write_manifest_entries(
        tmp_path,
        [ResolverManifestEntry(entry_id="first", target_url="https://example.test/first")],
    )

    manifest_path = write_manifest_entries(
        tmp_path,
        [ResolverManifestEntry(entry_id="second", target_url="https://example.test/second")],
    )

    assert manifest_path == tmp_path / ".strmline" / "resolver_manifest.json"
    assert resolve_manifest_target(tmp_path, "first") == "https://example.test/first"
    assert resolve_manifest_target(tmp_path, "second") == "https://example.test/second"


def test_resolve_manifest_target_rejects_missing_entry(tmp_path: Path) -> None:
    _ = write_manifest_entries(
        tmp_path,
        [ResolverManifestEntry(entry_id="first", target_url="https://example.test/first")],
    )

    with pytest.raises(RuntimeError, match="not found"):
        _ = resolve_manifest_target(tmp_path, "missing")
