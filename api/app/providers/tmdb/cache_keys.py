from __future__ import annotations

import json


def tmdb_cache_key(endpoint: str, params: dict[str, str] | None = None) -> str:
    safe_params = {key: value for key, value in (params or {}).items() if key.lower() != "api_key"}
    encoded_params = json.dumps(safe_params, sort_keys=True, separators=(",", ":"))
    return f"tmdb:v1:GET:{_normalize_endpoint(endpoint)}:{encoded_params}"


def _normalize_endpoint(endpoint: str) -> str:
    return f"/{endpoint.lstrip('/')}"
