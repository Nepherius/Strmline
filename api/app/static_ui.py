from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from starlette import status
from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles

RESERVED_PREFIXES = ("api/", "play/")


def mount_static_ui(app: FastAPI, static_dir: Path | None) -> None:
    if static_dir is None:
        return

    index_path = static_dir / "index.html"
    if not index_path.is_file():
        return
    index_html = index_path.read_text(encoding="utf-8")

    assets_path = static_dir / "_app"
    if assets_path.is_dir():
        app.mount("/_app", StaticFiles(directory=assets_path), name="static-assets")

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


def _index_handler(index_html: str) -> Callable[[], Awaitable[HTMLResponse]]:
    async def handler() -> HTMLResponse:
        return HTMLResponse(index_html)

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
