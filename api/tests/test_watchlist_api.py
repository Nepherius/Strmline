from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import watchlist as watchlist_api
from app.api.watchlist import WatchlistItemRequest
from app.db.repositories.watchlist import (
    WatchlistItemWrite,
    WatchlistRepository,
)


def watchlist_item() -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        tmdb_id=123,
        imdb_id="tt1234567",
        title="Example Series",
        year="2026",
        overview="An example.",
        poster_url="https://image.tmdb.org/example.jpg",
        media_type="series",
    )


@pytest.mark.asyncio
async def test_watchlist_routes_list_save_and_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = watchlist_item()
    session = AsyncMock(spec=AsyncSession)
    repository = SimpleNamespace(
        list_all=AsyncMock(return_value=(item,)),
        library_contains=AsyncMock(return_value=False),
        upsert=AsyncMock(return_value=item),
        delete=AsyncMock(return_value=True),
    )

    def repository_factory(_session: AsyncSession) -> SimpleNamespace:
        return repository

    monkeypatch.setattr(watchlist_api, "WatchlistRepository", repository_factory)

    listed = await watchlist_api.list_watchlist(session)
    saved = await watchlist_api.save_watchlist_item(
        WatchlistItemRequest(
            tmdb_id=123,
            imdb_id="tt1234567",
            title=" Example Series ",
            year="2026",
            overview="An example.",
            poster_url="https://image.tmdb.org/example.jpg",
            media_type="movie",
        ),
        session,
    )
    response = await watchlist_api.delete_watchlist_item("series", 123, session)

    assert listed[0].title == "Example Series"
    assert saved.tmdb_id == 123
    write = repository.upsert.await_args.args[0]
    assert write.title == "Example Series"
    assert write.media_type == "movie"
    repository.delete.assert_awaited_once_with("series", 123)
    assert response.status_code == 204
    assert session.commit.await_count == 2


@pytest.mark.asyncio
async def test_save_rejects_media_already_in_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = SimpleNamespace(
        library_contains=AsyncMock(return_value=True),
        upsert=AsyncMock(),
    )

    def repository_factory(_session: AsyncSession) -> SimpleNamespace:
        return repository

    monkeypatch.setattr(watchlist_api, "WatchlistRepository", repository_factory)

    with pytest.raises(watchlist_api.HTTPException) as caught:
        _ = await watchlist_api.save_watchlist_item(
            WatchlistItemRequest(tmdb_id=123, title="Human Vapor", media_type="series"),
            session,
        )

    assert caught.value.status_code == 409
    assert caught.value.detail == "This title is already in the library."
    repository.upsert.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_missing_watchlist_item_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = SimpleNamespace(delete=AsyncMock(return_value=False))

    def repository_factory(_session: AsyncSession) -> SimpleNamespace:
        return repository

    monkeypatch.setattr(watchlist_api, "WatchlistRepository", repository_factory)

    with pytest.raises(watchlist_api.HTTPException) as caught:
        _ = await watchlist_api.delete_watchlist_item("movie", 999, session)

    assert caught.value.status_code == 404


@pytest.mark.asyncio
async def test_watchlist_repository_upserts_and_deletes() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = WatchlistRepository(session)
    existing = watchlist_item()
    repository._by_identity = AsyncMock(  # pyright: ignore[reportPrivateUsage, reportAttributeAccessIssue]
        side_effect=[None, existing, existing, None]
    )
    write = WatchlistItemWrite(
        tmdb_id=123,
        imdb_id="tt1234567",
        title="Example Series",
        year="2026",
        overview="An example.",
        poster_url=None,
    )

    created = await repository.upsert(write)
    updated = await repository.upsert(write)
    removed = await repository.delete("series", 123)
    missing = await repository.delete("series", 999)

    assert created.title == "Example Series"
    assert updated is existing
    assert removed is True
    assert missing is False
    session.add.assert_called_once()
    session.delete.assert_awaited_once_with(existing)
