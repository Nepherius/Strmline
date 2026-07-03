from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.resolver.manifest import ResolverManifestError, resolve_manifest_target

router = APIRouter(tags=["resolver"])


@router.api_route("/play/{entry_id}", methods=["GET", "HEAD"])
async def play(entry_id: str, token: Annotated[str, Query(min_length=1)]) -> RedirectResponse:
    settings = get_settings()
    if settings.library_root is None or settings.resolver_token is None:
        raise HTTPException(status_code=503, detail="Resolver is not configured.")

    expected_token = settings.resolver_token.get_secret_value()
    if not secrets.compare_digest(token, expected_token):
        raise HTTPException(status_code=403, detail="Invalid resolver token.")

    try:
        target_url = resolve_manifest_target(settings.library_root, entry_id)
    except ResolverManifestError as error:
        raise HTTPException(status_code=404, detail="Resolver entry was not found.") from error

    return RedirectResponse(target_url)
