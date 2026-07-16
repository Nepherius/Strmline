from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_db_session
from app.db.models import WatchlistItem
from app.db.repositories.watchlist import WatchlistItemWrite, WatchlistRepository

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistItemRequest(BaseModel):
    tmdb_id: int = Field(ge=1)
    imdb_id: str | None = Field(default=None, min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=300)
    year: str | None = Field(default=None, max_length=20)
    overview: str = Field(default="", max_length=5000)
    poster_url: str | None = Field(default=None, max_length=1000, pattern=r"^https?://")
    media_type: Literal["movie", "series"] = "series"


class WatchlistItemResponse(BaseModel):
    id: int
    tmdb_id: int
    imdb_id: str | None
    title: str
    year: str | None
    overview: str
    poster_url: str | None
    media_type: str


@router.get("", response_model=list[WatchlistItemResponse])
async def list_watchlist(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[WatchlistItemResponse]:
    items = await WatchlistRepository(session).list_all()
    return [_response(item) for item in items]


@router.post("", response_model=WatchlistItemResponse)
async def save_watchlist_item(
    request: WatchlistItemRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WatchlistItemResponse:
    repository = WatchlistRepository(session)
    item = await repository.upsert(
        WatchlistItemWrite(
            tmdb_id=request.tmdb_id,
            imdb_id=request.imdb_id,
            title=request.title.strip(),
            year=request.year,
            overview=request.overview,
            poster_url=request.poster_url,
            media_type=request.media_type,
        )
    )
    await session.commit()
    return _response(item)


@router.delete("/{media_type}/{tmdb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist_item(
    media_type: Literal["movie", "series"],
    tmdb_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    removed = await WatchlistRepository(session).delete(media_type, tmdb_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Watchlist entry not found.")
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _response(item: WatchlistItem) -> WatchlistItemResponse:
    return WatchlistItemResponse(
        id=item.id,
        tmdb_id=item.tmdb_id,
        imdb_id=item.imdb_id,
        title=item.title,
        year=item.year,
        overview=item.overview,
        poster_url=item.poster_url,
        media_type=item.media_type,
    )
