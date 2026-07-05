from __future__ import annotations

import hashlib
import json
from typing import Any


def anilist_cache_key(
    *,
    operation_name: str,
    query: str,
    variables: dict[str, Any] | None = None,
) -> str:
    payload = {
        "operationName": operation_name,
        "query": " ".join(query.split()),
        "variables": variables or {},
    }
    encoded_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded_payload.encode("utf-8")).hexdigest()
    return f"anilist:v1:POST:{digest}"
