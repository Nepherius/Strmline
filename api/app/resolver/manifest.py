from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from app.library.atomic_io import atomic_write_text
from app.library.paths import ensure_within_root
from app.providers.torbox.files import TorBoxFile

MANIFEST_RELATIVE_PATH = Path(".strmline", "resolver_manifest.json")


class ResolverManifestError(RuntimeError):
    """Raised when resolver manifest state is missing or invalid."""


@dataclass(frozen=True, slots=True)
class ResolverManifestEntry:
    entry_id: str
    target_url: str


def resolver_entry_id(torbox_file: TorBoxFile) -> str:
    raw_key = f"{torbox_file.kind}:{torbox_file.item_id}:{torbox_file.file_id}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]


def resolver_playback_url(base_url: str, token: str, entry_id: str) -> str:
    return f"{base_url.rstrip('/')}/play/{entry_id}?token={token}"


def write_manifest_entries(library_root: Path, entries: list[ResolverManifestEntry]) -> Path:
    manifest_path = _manifest_path(library_root)
    existing_entries = _read_entries(manifest_path)
    for entry in entries:
        existing_entries[entry.entry_id] = entry.target_url

    payload = {
        "version": 1,
        "entries": existing_entries,
    }
    atomic_write_text(
        manifest_path,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )
    return manifest_path


def resolve_manifest_target(library_root: Path, entry_id: str) -> str:
    entries = _read_entries(_manifest_path(library_root))
    target_url = entries.get(entry_id)
    if target_url is None:
        msg = "Resolver entry was not found."
        raise ResolverManifestError(msg)
    return target_url


def _manifest_path(library_root: Path) -> Path:
    return ensure_within_root(library_root, library_root / MANIFEST_RELATIVE_PATH)


def _read_entries(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(payload, dict):
        msg = "Resolver manifest was not a JSON object."
        raise ResolverManifestError(msg)
    raw_payload = cast(dict[str, object], payload)
    raw_entries = raw_payload.get("entries")
    if not isinstance(raw_entries, dict):
        msg = "Resolver manifest entries were invalid."
        raise ResolverManifestError(msg)
    return _typed_entries(cast(dict[Any, Any], raw_entries))


def _typed_entries(raw_entries: dict[Any, Any]) -> dict[str, str]:
    entries: dict[str, str] = {}
    for key, value in raw_entries.items():
        if not isinstance(key, str) or not isinstance(value, str):
            msg = "Resolver manifest contained an invalid entry."
            raise ResolverManifestError(msg)
        entries[key] = value
    return entries
