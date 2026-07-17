from __future__ import annotations

import re
import unicodedata

INFO_HASH_PATTERN = re.compile(r"^[A-Za-z0-9]{20,100}$")
TITLE_TOKEN = re.compile(r"[\w]+", re.UNICODE)


def normalize_info_hash(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not INFO_HASH_PATTERN.fullmatch(candidate):
        return None
    return candidate.casefold()


def normalize_source_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip("/").casefold()
    return re.sub(r"/+", "/", normalized)


def normalize_title_for_identity(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(TITLE_TOKEN.findall(normalized))


def normalize_title_for_duplicate_detection(value: str) -> str:
    return normalize_title_for_identity(value)
