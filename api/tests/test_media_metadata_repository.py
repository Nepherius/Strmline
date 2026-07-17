from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.db.models import MediaExternalIdentity, MediaItem
from app.db.repositories.media_metadata import (
    MediaMetadataRepository,
    _path_matches_prefix,  # pyright: ignore[reportPrivateUsage]
    escape_like,
)
from app.domain.media_identity import IdentityAuthority


class FakeResult:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self._rows

    def scalars(self) -> Iterator[object]:
        return (row[0] for row in self._rows)


class FakeSession:
    def __init__(self, results: list[FakeResult]) -> None:
        self._results = results

    async def execute(self, _statement: object) -> FakeResult:
        return self._results.pop(0)


def _media(
    media_item_id: int,
    *,
    content_kind: str = "series",
    title: str = "From",
) -> MediaItem:
    return MediaItem(id=media_item_id, content_kind=content_kind, title=title, year=None)


def _identity(media_item_id: int, external_id: str) -> MediaExternalIdentity:
    return MediaExternalIdentity(
        id=media_item_id,
        media_item_id=media_item_id,
        provider="tmdb",
        provider_media_kind="tv",
        external_id=external_id,
        authority=IdentityAuthority.SEARCH_CONFIRMED.value,
        authoritative=True,
    )


@pytest.mark.asyncio
async def test_media_location_is_derived_from_stable_media_id() -> None:
    repository = MediaMetadataRepository(
        FakeSession(
            [
                FakeResult(
                    [
                        ("anime/Kaiju No. 8/Season 01/S01E01.strm",),
                        ("anime/Kaiju No. 8/Season 02/S02E01.strm",),
                    ]
                )
            ]
        )  # type: ignore[arg-type]
    )

    location = await repository.location_for_media_item(207468)

    assert location is not None
    assert location.media_item_id == 207468
    assert location.category == "anime"
    assert location.relative_prefix == "anime/Kaiju No. 8"


@pytest.mark.asyncio
async def test_media_metadata_repository_requires_one_stable_media_item() -> None:
    first = _media(1)
    second = _media(2)
    first_identity = _identity(1, "1")
    second_identity = _identity(2, "2")
    single = await MediaMetadataRepository(
        FakeSession(
            [
                FakeResult(
                    [
                        (
                            first,
                            first_identity,
                            "shows/From/Season 01/From - S01E01.strm",
                        ),
                        (
                            first,
                            first_identity,
                            "shows/From/Season 02/From - S02E01.strm",
                        ),
                    ]
                )
            ]
        )  # type: ignore[arg-type]
    ).find_for_library_prefix("shows/From")
    multiple = await MediaMetadataRepository(
        FakeSession(
            [
                FakeResult(
                    [
                        (first, first_identity, "shows/From/Season 01/S01E01.strm"),
                        (second, second_identity, "shows/From/Season 02/S02E01.strm"),
                    ]
                )
            ]
        )  # type: ignore[arg-type]
    ).find_for_library_prefix("shows/From")

    assert single is not None
    assert single.media_item is first
    assert single.tmdb_id == "1"
    assert multiple is None


@pytest.mark.asyncio
async def test_media_metadata_repository_maps_prefixes_to_stable_records() -> None:
    movie = _media(1, content_kind="movie", title="Always")
    show = _media(2)
    repository = MediaMetadataRepository(
        FakeSession(
            [
                FakeResult(
                    [
                        (
                            movie,
                            _identity(1, "1"),
                            "movies/Always (2011)/Always (2011).strm",
                        ),
                        (
                            show,
                            _identity(2, "2"),
                            "shows/From/Season 01/From - S01E01.strm",
                        ),
                    ]
                )
            ]
        )  # type: ignore[arg-type]
    )

    records = await repository.records_for_library_prefixes(
        {"movies/Always (2011)", "shows/From", "anime/Missing"}
    )

    assert records["movies/Always (2011)"].media_item.id == 1
    assert records["shows/From"].tmdb_id == "2"


def test_library_prefix_like_pattern_escapes_wildcards() -> None:
    assert escape_like(r"shows/100%_Real\Title") == r"shows/100\%\_Real\\Title"
    expression = _path_matches_prefix("shows/100%_Real")
    compiled = expression.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )

    compiled_sql = str(compiled)
    assert r"\%" in compiled_sql
    assert r"\_" in compiled_sql
    assert "ESCAPE" in compiled_sql


def test_library_record_query_uses_external_identity_join() -> None:
    statement: Any = MediaMetadataRepository._library_record_query()  # pyright: ignore[reportPrivateUsage]
    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "media_external_identities" in compiled
    assert "media_external_identities.provider" in compiled
