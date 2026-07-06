"""Parse structured metadata from AIOStreams stream title and description strings."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParsedStream:
    """Structured metadata extracted from a Stremio stream response."""

    quality: str | None
    codec: str | None
    hdr: str | None
    audio: str | None
    size_bytes: int | None
    size_label: str | None
    source: str | None
    language: str | None


_QUALITY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b2160p\b", re.IGNORECASE), "4K"),
    (re.compile(r"\b4[Kk]\b"), "4K"),
    (re.compile(r"\bUHD\b", re.IGNORECASE), "4K"),
    (re.compile(r"\b1080p\b", re.IGNORECASE), "1080p"),
    (re.compile(r"\b720p\b", re.IGNORECASE), "720p"),
    (re.compile(r"\b480p\b", re.IGNORECASE), "480p"),
    (re.compile(r"\b360p\b", re.IGNORECASE), "360p"),
    (re.compile(r"\bCAM\b"), "CAM"),
    (re.compile(r"\bTS\b"), "TS"),
    (re.compile(r"\bSCR(?:EENER)?\b", re.IGNORECASE), "SCR"),
)

_CODEC_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[Hh]\.?265\b"), "H.265"),
    (re.compile(r"\bHEVC\b", re.IGNORECASE), "H.265"),
    (re.compile(r"\b[Xx]\.?265\b"), "H.265"),
    (re.compile(r"\bAV1\b", re.IGNORECASE), "AV1"),
    (re.compile(r"\b[Hh]\.?264\b"), "H.264"),
    (re.compile(r"\bAVC\b", re.IGNORECASE), "H.264"),
    (re.compile(r"\b[Xx]\.?264\b"), "H.264"),
    (re.compile(r"\bVP9\b", re.IGNORECASE), "VP9"),
    (re.compile(r"\bXviD\b", re.IGNORECASE), "XviD"),
)

_HDR_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bDolby\s*Vision\b", re.IGNORECASE), "DV"),
    (re.compile(r"\bDV\b"), "DV"),
    (re.compile(r"\bDoVi\b", re.IGNORECASE), "DV"),
    (re.compile(r"\bHDR10\+", re.IGNORECASE), "HDR10+"),
    (re.compile(r"\bHDR10(?!\+)\b", re.IGNORECASE), "HDR10"),
    (re.compile(r"\bHDR\b", re.IGNORECASE), "HDR"),
    (re.compile(r"\bSDR\b", re.IGNORECASE), "SDR"),
)

_AUDIO_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bAtmos\b", re.IGNORECASE), "Atmos"),
    (re.compile(r"\bTrueHD\b", re.IGNORECASE), "TrueHD"),
    (re.compile(r"\bDTS[\s-]?HD(?:[\s.]?MA)?\b", re.IGNORECASE), "DTS-HD"),
    (re.compile(r"\bDTS\b", re.IGNORECASE), "DTS"),
    (re.compile(r"\bFLAC\b", re.IGNORECASE), "FLAC"),
    (re.compile(r"\bDD\+?\s*5\.1\b", re.IGNORECASE), "DD5.1"),
    (re.compile(r"\bDD[P+]\b", re.IGNORECASE), "DD+"),
    (re.compile(r"\bEAC[\s-]?3\b", re.IGNORECASE), "DD+"),
    (re.compile(r"\bAC[\s-]?3\b", re.IGNORECASE), "AC3"),
    (re.compile(r"\bAAC\b", re.IGNORECASE), "AAC"),
)

_SOURCE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bBlu[\s-]?[Rr]ay\b"), "BluRay"),
    (re.compile(r"\bBDRip\b", re.IGNORECASE), "BluRay"),
    (re.compile(r"\bBRRip\b", re.IGNORECASE), "BluRay"),
    (re.compile(r"\bREMUX\b", re.IGNORECASE), "Remux"),
    (re.compile(r"\bWEB[\s-]?DL\b", re.IGNORECASE), "WEB-DL"),
    (re.compile(r"\bWEBRip\b", re.IGNORECASE), "WEBRip"),
    (re.compile(r"\bWEB\b"), "WEB"),
    (re.compile(r"\bHDRip\b", re.IGNORECASE), "HDRip"),
    (re.compile(r"\bDVDRip\b", re.IGNORECASE), "DVDRip"),
    (re.compile(r"\bHDTV\b", re.IGNORECASE), "HDTV"),
)

_LANGUAGE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bMulti\b", re.IGNORECASE), "Multi"),
    (re.compile(r"\bDual[\s-]?Audio\b", re.IGNORECASE), "Dual"),
    (re.compile(r"\bEnglish\b", re.IGNORECASE), "English"),
    (re.compile(r"\bFrench\b", re.IGNORECASE), "French"),
    (re.compile(r"\bGerman\b", re.IGNORECASE), "German"),
    (re.compile(r"\bSpanish\b", re.IGNORECASE), "Spanish"),
    (re.compile(r"\bItalian\b", re.IGNORECASE), "Italian"),
    (re.compile(r"\bPortuguese\b", re.IGNORECASE), "Portuguese"),
    (re.compile(r"\bJapanese\b", re.IGNORECASE), "Japanese"),
    (re.compile(r"\bKorean\b", re.IGNORECASE), "Korean"),
    (re.compile(r"\bChinese\b", re.IGNORECASE), "Chinese"),
    (re.compile(r"\bHindi\b", re.IGNORECASE), "Hindi"),
)

_SIZE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(GB|MB|TB)",
    re.IGNORECASE,
)

_SIZE_MULTIPLIERS: dict[str, int] = {
    "tb": 1024 * 1024 * 1024 * 1024,
    "gb": 1024 * 1024 * 1024,
    "mb": 1024 * 1024,
}

_IMDB_ID_PATTERN = re.compile(r"^tt\d+$")


def parse_stream(
    *,
    title: str | None,
    description: str | None,
    name: str | None,
    filename: str | None,
    video_size: int | None,
) -> ParsedStream:
    """Extract structured metadata from stream text fields."""
    combined = _combine_fields(title, description, name, filename)

    size_bytes = video_size
    size_label: str | None = None
    if size_bytes is not None:
        size_label = _format_bytes(size_bytes)
    else:
        parsed_size = _parse_size_from_text(combined)
        if parsed_size is not None:
            size_bytes, size_label = parsed_size

    return ParsedStream(
        quality=_first_match(combined, _QUALITY_PATTERNS),
        codec=_first_match(combined, _CODEC_PATTERNS),
        hdr=_first_match(combined, _HDR_PATTERNS),
        audio=_first_match(combined, _AUDIO_PATTERNS),
        size_bytes=size_bytes,
        size_label=size_label,
        source=_first_match(combined, _SOURCE_PATTERNS),
        language=_first_match(combined, _LANGUAGE_PATTERNS),
    )


def is_imdb_id(value: str) -> bool:
    """Check whether a string looks like an IMDB ID (e.g. tt1375666)."""
    return bool(_IMDB_ID_PATTERN.match(value.strip()))


def _first_match(
    text: str,
    patterns: tuple[tuple[re.Pattern[str], str], ...],
) -> str | None:
    for pattern, label in patterns:
        if pattern.search(text):
            return label
    return None


def _combine_fields(*fields: str | None) -> str:
    parts = [field for field in fields if field and field.strip()]
    return " ".join(parts)


def _parse_size_from_text(text: str) -> tuple[int, str] | None:
    match = _SIZE_PATTERN.search(text)
    if match is None:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower()
    multiplier = _SIZE_MULTIPLIERS.get(unit)
    if multiplier is None:
        return None
    size_bytes = int(value * multiplier)
    return size_bytes, f"{value:g} {match.group(2).upper()}"


def _format_bytes(size_bytes: int) -> str:
    if size_bytes >= _SIZE_MULTIPLIERS["tb"]:
        return f"{size_bytes / _SIZE_MULTIPLIERS['tb']:.1f} TB"
    if size_bytes >= _SIZE_MULTIPLIERS["gb"]:
        return f"{size_bytes / _SIZE_MULTIPLIERS['gb']:.1f} GB"
    return f"{size_bytes / _SIZE_MULTIPLIERS['mb']:.1f} MB"
