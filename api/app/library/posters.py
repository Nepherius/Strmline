from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.library.atomic_io import atomic_write_bytes
from app.library.paths import ensure_within_root

POSTER_STEM = "poster"
IMAGE_SIGNATURE_BYTES = 12
POSTER_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
ARTWORK_DIRECTORY = "artwork"


@dataclass(frozen=True, slots=True)
class PosterImage:
    content: bytes
    suffix: str


@dataclass(frozen=True, slots=True)
class PosterCacheResult:
    downloaded: int
    cached: int
    failed: int


class PosterFetcher(Protocol):
    async def fetch(self, poster_path: str) -> PosterImage:
        """Fetch one validated TMDB poster."""
        ...


class PosterSource(Protocol):
    @property
    def tmdb_id(self) -> str | None: ...

    @property
    def tmdb_poster_path(self) -> str | None: ...


async def cache_missing_posters(
    library_root: Path,
    sources: Iterable[PosterSource],
    fetcher: PosterFetcher,
) -> PosterCacheResult:
    """Populate missing artwork only; existing local posters are never fetched again."""
    downloaded = 0
    cached = 0
    failed = 0
    seen_directories: set[Path] = set()

    for source in sources:
        if source.tmdb_id is None or source.tmdb_poster_path is None:
            continue
        artwork_directory = artwork_directory_for_tmdb_id(library_root, source.tmdb_id)
        if artwork_directory in seen_directories:
            continue
        seen_directories.add(artwork_directory)
        if find_poster(library_root, artwork_directory):
            cached += 1
            continue
        try:
            image = await fetcher.fetch(source.tmdb_poster_path)
            _ = write_poster(library_root, artwork_directory, image)
        except (OSError, ValueError, RuntimeError):
            failed += 1
        else:
            downloaded += 1

    return PosterCacheResult(downloaded=downloaded, cached=cached, failed=failed)


async def refresh_posters(
    library_root: Path,
    fetcher: PosterFetcher,
    poster_path: str,
    tmdb_id: str,
) -> int:
    """Replace the locally cached poster for one TMDB media item."""
    image = await fetcher.fetch(poster_path)
    artwork_directory = artwork_directory_for_tmdb_id(library_root, tmdb_id)
    _ = write_poster(library_root, artwork_directory, image)
    return 1


def poster_for_tmdb_id(root: Path, tmdb_id: str) -> Path | None:
    return find_poster(root, artwork_directory_for_tmdb_id(root, tmdb_id))


def artwork_directory_for_tmdb_id(root: Path, tmdb_id: str) -> Path:
    if not tmdb_id.isdecimal():
        msg = "TMDB ID is invalid."
        raise ValueError(msg)
    return ensure_within_root(root, root / ARTWORK_DIRECTORY / f"tmdb-{tmdb_id}")


def find_poster(root: Path, directory: Path) -> Path | None:
    safe_directory = ensure_within_root(root, directory)
    for suffix in POSTER_SUFFIXES:
        candidate = ensure_within_root(root, safe_directory / f"{POSTER_STEM}{suffix}")
        if not candidate.is_file():
            continue
        try:
            signature = candidate.read_bytes()[:IMAGE_SIGNATURE_BYTES]
        except OSError:
            continue
        if _is_supported_image(signature, suffix):
            return candidate
    return None


def write_poster(root: Path, directory: Path, image: PosterImage) -> Path:
    if image.suffix not in POSTER_SUFFIXES:
        msg = "Poster format is not supported."
        raise ValueError(msg)
    if not image.content:
        msg = "Poster content is empty."
        raise ValueError(msg)
    if not _is_supported_image(image.content[:IMAGE_SIGNATURE_BYTES], image.suffix):
        msg = "Poster content does not match its image format."
        raise ValueError(msg)

    safe_directory = ensure_within_root(root, directory)
    target = ensure_within_root(root, safe_directory / f"{POSTER_STEM}{image.suffix}")
    atomic_write_bytes(target, image.content)
    for suffix in POSTER_SUFFIXES:
        stale = ensure_within_root(root, safe_directory / f"{POSTER_STEM}{suffix}")
        if stale != target and stale.is_file():
            stale.unlink()
    return target


def _is_supported_image(content: bytes, suffix: str) -> bool:
    if suffix in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if suffix == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix == ".webp":
        return (
            len(content) >= IMAGE_SIGNATURE_BYTES
            and content[:4] == b"RIFF"
            and content[8:IMAGE_SIGNATURE_BYTES] == b"WEBP"
        )
    return False
