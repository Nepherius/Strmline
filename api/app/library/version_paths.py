from __future__ import annotations

import re
from pathlib import Path

from app.library.paths import clean_path_segment

_VERSION_TOKENS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)(?<!\w)2160p(?!\w)"), "2160p"),
    (re.compile(r"(?i)(?<!\w)1080p(?!\w)"), "1080p"),
    (re.compile(r"(?i)(?<!\w)720p(?!\w)"), "720p"),
    (re.compile(r"(?i)(?<!\w)(?:uhd[ ._-]*blu[ ._-]*ray|uhd)(?!\w)"), "UHD"),
    (re.compile(r"(?i)(?<!\w)remux(?!\w)"), "Remux"),
    (re.compile(r"(?i)(?<!\w)blu[ ._-]*ray(?!\w)"), "BluRay"),
    (re.compile(r"(?i)(?<!\w)web[ ._-]*dl(?!\w)"), "WEB-DL"),
    (re.compile(r"(?i)(?<!\w)web[ ._-]*rip(?!\w)"), "WEBRip"),
    (re.compile(r"(?i)(?<!\w)hdtv(?!\w)"), "HDTV"),
    (re.compile(r"(?i)(?<!\w)(?:dolby[ ._-]*vision|dovi|dv)(?!\w)"), "DV"),
    (re.compile(r"(?i)(?<!\w)hdr10[+]?|(?<!\w)hdr(?!\w)"), "HDR"),
    (re.compile(r"(?i)(?<!\w)(?:x265|h[ ._-]*265|hevc)(?!\w)"), "HEVC"),
    (re.compile(r"(?i)(?<!\w)(?:x264|h[ ._-]*264|avc)(?!\w)"), "H264"),
    (re.compile(r"(?i)(?<!\w)av1(?!\w)"), "AV1"),
)


def alternate_version_path(
    canonical_path: Path,
    source_name: str,
    *,
    unique_suffix: str | None = None,
) -> Path:
    """Return a player-friendly sibling path for another release of the same media."""
    label = version_label(source_name)
    suffix = f" [{unique_suffix}]" if unique_suffix is not None else ""
    return canonical_path.with_name(
        f"{canonical_path.stem} - {label}{suffix}{canonical_path.suffix}"
    )


def version_label(source_name: str) -> str:
    labels = [label for pattern, label in _VERSION_TOKENS if pattern.search(source_name)]
    if not labels:
        return "Alternate"
    return clean_path_segment(" ".join(dict.fromkeys(labels)), fallback="Alternate")
