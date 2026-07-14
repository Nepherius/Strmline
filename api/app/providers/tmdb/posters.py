from __future__ import annotations

import re
from pathlib import PurePosixPath

import httpx

from app.library.posters import PosterImage

POSTER_BASE_URL = "https://image.tmdb.org/t/p/w500"
MAX_POSTER_BYTES = 10 * 1024 * 1024
POSTER_PATH = re.compile(r"^/[A-Za-z0-9._-]+$")
CONTENT_TYPE_SUFFIX = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class TmdbPosterError(RuntimeError):
    """Raised when TMDB poster data cannot be safely cached."""


class TmdbPosterClient:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def fetch(self, poster_path: str) -> PosterImage:
        if not POSTER_PATH.fullmatch(poster_path):
            raise TmdbPosterError("TMDB poster path is invalid.")
        async with httpx.AsyncClient(
            base_url=POSTER_BASE_URL,
            timeout=self._timeout_seconds,
            transport=self._transport,
        ) as client:
            try:
                response = await client.get(poster_path)
            except httpx.HTTPError as error:
                raise TmdbPosterError("TMDB poster request failed.") from error
        if response.is_error:
            raise TmdbPosterError("TMDB poster request failed.")
        if len(response.content) > MAX_POSTER_BYTES:
            raise TmdbPosterError("TMDB poster response is too large.")
        suffix = _poster_suffix(response.headers.get("content-type"), poster_path)
        if suffix is None:
            raise TmdbPosterError("TMDB poster response is not a supported image.")
        return PosterImage(content=response.content, suffix=suffix)


def _poster_suffix(content_type: str | None, poster_path: str) -> str | None:
    if content_type is not None:
        suffix = CONTENT_TYPE_SUFFIX.get(content_type.split(";", 1)[0].strip().lower())
        if suffix is not None:
            return suffix
    suffix = PurePosixPath(poster_path).suffix.lower()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".webp"} else None
