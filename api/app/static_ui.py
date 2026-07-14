from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from starlette import status
from starlette.responses import HTMLResponse, Response
from starlette.staticfiles import StaticFiles

RESERVED_PREFIXES = ("api/", "play/")
_INLINE_SCRIPT_PATTERN = re.compile(
    r"<script(?P<attributes>[^>]*)>(?P<body>.*?)</script>", re.IGNORECASE | re.DOTALL
)
_SCRIPT_SOURCE_ATTRIBUTE_PATTERN = re.compile(r"\bsrc\s*=", re.IGNORECASE)


def mount_static_ui(app: FastAPI, static_dir: Path | None) -> tuple[str, ...]:
    if static_dir is None:
        return ()

    index_path = static_dir / "index.html"
    if not index_path.is_file():
        return ()
    index_html = index_path.read_text(encoding="utf-8")

    assets_path = static_dir / "_app"
    if assets_path.is_dir():
        app.mount("/_app", StaticFiles(directory=assets_path), name="static-assets")

    favicon_path = static_dir / "favicon.svg"
    if favicon_path.is_file():
        app.add_api_route(
            "/favicon.svg",
            _asset_handler(favicon_path.read_bytes(), "image/svg+xml"),
            methods=["GET"],
            include_in_schema=False,
        )

    app.add_api_route(
        "/",
        _index_handler(index_html),
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        "/{path:path}",
        _fallback_handler(index_html),
        methods=["GET"],
        include_in_schema=False,
    )
    return inline_script_hashes(index_html)


def inline_script_hashes(index_html: str) -> tuple[str, ...]:
    hashes = {
        _script_hash(match.group("body"))
        for match in _INLINE_SCRIPT_PATTERN.finditer(index_html)
        if not _SCRIPT_SOURCE_ATTRIBUTE_PATTERN.search(match.group("attributes"))
    }
    return tuple(sorted(hashes))


def _script_hash(script: str) -> str:
    digest = hashlib.sha256(script.encode("utf-8")).digest()
    return f"sha256-{base64.b64encode(digest).decode('ascii')}"


def _index_handler(index_html: str) -> Callable[[], Awaitable[HTMLResponse]]:
    async def handler() -> HTMLResponse:
        return HTMLResponse(index_html)

    return handler


def _asset_handler(content: bytes, media_type: str) -> Callable[[], Awaitable[Response]]:
    async def handler() -> Response:
        return Response(content, media_type=media_type)

    return handler


def _fallback_handler(index_html: str) -> Callable[[str], Awaitable[HTMLResponse]]:
    async def handler(path: str) -> HTMLResponse:
        if _reserved_path(path) or _asset_path(path):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return HTMLResponse(index_html)

    return handler


def _reserved_path(path: str) -> bool:
    return path.startswith(RESERVED_PREFIXES)


def _asset_path(path: str) -> bool:
    return "." in Path(path).name
