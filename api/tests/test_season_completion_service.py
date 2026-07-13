from dataclasses import replace
from typing import Any, cast

import pytest

from app.core.config import Settings
from app.db.repositories.settings import SettingsSnapshot
from app.providers.aiostreams.client import AioStreamsClient, AioStreamsClientError
from app.providers.tmdb.client import TmdbClientError
from app.providers.tmdb.metadata import TmdbMetadataService
from app.providers.torbox.client import TorBoxAPIError, TorBoxClient
from app.season_completion import service
from app.season_completion.discovery import AioStreamsRequestLimiter
from app.season_completion.inventory import LibraryShow
from app.season_completion.ranking import CompletionCandidate, EpisodeRef


class FakeMetadata:
    async def get_json(
        self,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        _ = params
        if endpoint == "/tv/42":
            return {"seasons": [{"season_number": 0}, {"season_number": 1}]}
        if endpoint == "/tv/42/external_ids":
            return {"imdb_id": "tt1234567"}
        if endpoint == "/tv/42/season/1":
            return {
                "episodes": [
                    {"season_number": 1, "episode_number": 1, "air_date": "2020-01-01"},
                    {"season_number": 1, "episode_number": 2, "air_date": "2020-01-08"},
                    {"season_number": 1, "episode_number": 3, "air_date": "2020-01-15"},
                ]
            }
        raise AssertionError(endpoint)

    async def get_season_completion_json(
        self,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return await self.get_json(endpoint, params=params)


class FakeTorBox:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []

    async def create_torrent(
        self,
        *,
        magnet: str,
        name: str | None = None,
        add_only_if_cached: bool = True,
    ) -> dict[str, Any]:
        self.created.append(
            {"magnet": magnet, "name": name, "add_only_if_cached": add_only_if_cached}
        )
        return {"torrent_id": 10}


@pytest.mark.asyncio
async def test_complete_show_adds_shared_pack_once(monkeypatch: pytest.MonkeyPatch) -> None:
    missing = frozenset({EpisodeRef(1, 2), EpisodeRef(1, 3)})
    pack = CompletionCandidate(
        source_id="hash:pack-hash",
        info_hash="pack-hash",
        title="Show.Group.S01.pack",
        release_family="show group s01e",
        episodes=missing,
        cached=True,
    )

    async def fake_discover(**kwargs: object) -> list[CompletionCandidate]:
        assert kwargs["imdb_id"] == "tt1234567"
        assert kwargs["missing"] == missing
        return [pack]

    monkeypatch.setattr(service, "discover_candidates", fake_discover)
    torbox = FakeTorBox()
    show = LibraryShow(
        media_item_id=1,
        tmdb_id="42",
        title="Show",
        episodes=frozenset({EpisodeRef(1, 1)}),
        filenames_by_season={1: ("Show.Group.S01E01.mkv",)},
    )

    result = await service._complete_show(  # pyright: ignore[reportPrivateUsage]
        show=show,
        metadata=cast(TmdbMetadataService, FakeMetadata()),
        aiostreams=cast(AioStreamsClient, object()),
        torbox=cast(TorBoxClient, torbox),
        allow_uncached=False,
        already_added=set(),
        request_limiter=cast(AioStreamsRequestLimiter, object()),
    )

    assert result == (2, 1, 0)
    assert len(torbox.created) == 1
    assert torbox.created[0]["add_only_if_cached"] is True


@pytest.mark.asyncio
async def test_complete_show_rejects_candidate_for_another_show(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unrelated = CompletionCandidate(
        source_id="hash:bridgerton-hash",
        info_hash="bridgerton-hash",
        title="Bridgerton.S03E01.2160p.mkv",
        release_family="bridgerton s03e",
        episodes=frozenset({EpisodeRef(1, 2), EpisodeRef(1, 3)}),
        cached=True,
    )

    async def fake_discover(**kwargs: object) -> list[CompletionCandidate]:
        _ = kwargs
        return [unrelated]

    monkeypatch.setattr(service, "discover_candidates", fake_discover)
    torbox = FakeTorBox()
    show = LibraryShow(
        media_item_id=1,
        tmdb_id="42",
        title="Show",
        episodes=frozenset({EpisodeRef(1, 1)}),
        filenames_by_season={1: ("Show.Group.S01E01.mkv",)},
    )

    result = await service._complete_show(  # pyright: ignore[reportPrivateUsage]
        show=show,
        metadata=cast(TmdbMetadataService, FakeMetadata()),
        aiostreams=cast(AioStreamsClient, object()),
        torbox=cast(TorBoxClient, torbox),
        allow_uncached=False,
        already_added=set(),
        request_limiter=cast(AioStreamsRequestLimiter, object()),
    )

    assert result == (2, 0, 2)
    assert torbox.created == []


@pytest.mark.asyncio
async def test_complete_show_accepts_provider_folder_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = frozenset({EpisodeRef(1, 2), EpisodeRef(1, 3)})
    pack = CompletionCandidate(
        source_id="hash:bookworm-hash",
        info_hash="bookworm-hash",
        title="[sam] Ascendance of a Bookworm - 01.mkv",
        release_family=None,
        episodes=missing,
        cached=True,
        match_labels=(
            "[sam] Ascendance of a Bookworm - 01.mkv",
            "Ascendance Of A Bookworm S01 \u2022 E01",
        ),
    )

    async def fake_discover(**kwargs: object) -> list[CompletionCandidate]:
        _ = kwargs
        return [pack]

    monkeypatch.setattr(service, "discover_candidates", fake_discover)
    torbox = FakeTorBox()
    show = LibraryShow(
        media_item_id=1,
        tmdb_id="42",
        title="Ascendance of a Bookworm",
        episodes=frozenset({EpisodeRef(1, 1)}),
        filenames_by_season={1: ("Ascendance.of.a.Bookworm.S01E01.mkv",)},
    )

    result = await service._complete_show(  # pyright: ignore[reportPrivateUsage]
        show=show,
        metadata=cast(TmdbMetadataService, FakeMetadata()),
        aiostreams=cast(AioStreamsClient, object()),
        torbox=cast(TorBoxClient, torbox),
        allow_uncached=False,
        already_added=set(),
        request_limiter=cast(AioStreamsRequestLimiter, object()),
    )

    assert result == (2, 1, 0)
    assert len(torbox.created) == 1


@pytest.mark.asyncio
async def test_add_candidate_triggers_cached_aiostreams_action() -> None:
    triggered: list[str] = []

    class FakeAioStreams:
        async def trigger_stream_url(self, url: str) -> object:
            triggered.append(url)
            return object()

    candidate = CompletionCandidate(
        source_id="action:cached",
        info_hash=None,
        action_url="https://example.invalid/torbox-action",
        title="Show.S01E01.mkv",
        release_family="show s01e",
        episodes=frozenset({EpisodeRef(1, 1)}),
        cached=True,
    )

    await service._add_candidate(  # pyright: ignore[reportPrivateUsage]
        candidate=candidate,
        aiostreams=cast(AioStreamsClient, FakeAioStreams()),
        torbox=cast(TorBoxClient, FakeTorBox()),
    )

    assert triggered == ["https://example.invalid/torbox-action"]


@pytest.mark.asyncio
async def test_complete_show_requires_tmdb_identity() -> None:
    show = LibraryShow(
        media_item_id=1,
        tmdb_id=None,
        title="Unknown Show",
        episodes=frozenset({EpisodeRef(1, 1)}),
        filenames_by_season={},
    )

    with pytest.raises(TmdbClientError, match="TMDB identity"):
        _ = await service._complete_show(  # pyright: ignore[reportPrivateUsage]
            show=show,
            metadata=cast(TmdbMetadataService, FakeMetadata()),
            aiostreams=cast(AioStreamsClient, object()),
            torbox=cast(TorBoxClient, FakeTorBox()),
            allow_uncached=False,
            already_added=set(),
            request_limiter=cast(AioStreamsRequestLimiter, object()),
        )


def test_safe_provider_errors_do_not_expose_provider_details() -> None:
    assert (
        service._safe_provider_error(  # pyright: ignore[reportPrivateUsage]
            AioStreamsClientError("sensitive URL")
        )
        == "AIOStreams episode lookup failed."
    )
    assert (
        service._missing_configuration(  # pyright: ignore[reportPrivateUsage]
            torbox_key="key",
            tmdb_key=None,
            aiostreams_url=None,
        )
        == "Season auto-complete requires configured TMDB, AIOStreams providers."
    )
    assert (
        service._safe_provider_error(  # pyright: ignore[reportPrivateUsage]
            TmdbClientError("TMDB failed")
        )
        == "TMDB failed"
    )
    assert (
        service._safe_provider_error(  # pyright: ignore[reportPrivateUsage]
            TorBoxAPIError("sensitive provider detail")
        )
        == "TorBox season acquisition failed."
    )


@pytest.mark.asyncio
async def test_show_rate_limit_waits_for_remaining_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits: list[float] = []

    async def fake_sleep(delay: float) -> None:
        waits.append(delay)

    monkeypatch.setattr(service, "monotonic", lambda: 100.0)
    monkeypatch.setattr(service.asyncio, "sleep", fake_sleep)

    await service._wait_for_next_show(100.0, 1)  # pyright: ignore[reportPrivateUsage]

    assert waits == [60.0]


def test_show_diagnostic_includes_show_title() -> None:
    assert (
        service._show_diagnostic(  # pyright: ignore[reportPrivateUsage]
            "Example Show",
            "No eligible sources were found for 30 missing episode(s).",
        )
        == "Example Show: No eligible sources were found for 30 missing episode(s)."
    )


@pytest.mark.asyncio
async def test_run_records_missing_provider_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, object] = {}
    monkeypatch.setattr(
        service,
        "AppSettingsRepository",
        _settings_repository(_snapshot(), torbox_key="key", tmdb_key=None, aiostreams_url=None),
    )
    monkeypatch.setattr(service, "SyncStateRepository", _sync_state_repository(recorded))

    summary = await service.run_season_completion(
        cast(Any, object()),
        Settings(),
    )

    assert summary.checked_shows == 0
    assert "configured TMDB, AIOStreams" in summary.diagnostics[0][1]
    assert recorded["diagnostics"] == summary.diagnostics


@pytest.mark.asyncio
async def test_run_skips_when_series_categories_are_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, object] = {}
    monkeypatch.setattr(
        service,
        "AppSettingsRepository",
        _settings_repository(
            _snapshot(shows_enabled=False, anime_enabled=False),
            torbox_key="key",
            tmdb_key="key",
            aiostreams_url="https://aio.example/manifest.json",
        ),
    )
    monkeypatch.setattr(service, "SyncStateRepository", _sync_state_repository(recorded))

    summary = await service.run_season_completion(cast(Any, object()), Settings())

    assert "shows and anime are disabled" in summary.diagnostics[0][1]


def _snapshot(**changes: object) -> SettingsSnapshot:
    return replace(
        SettingsSnapshot(
            base_url="http://test",
            library_root="/library",
            movies_enabled=True,
            shows_enabled=True,
            anime_enabled=True,
            playback_mode="resolver",
            sync_interval_minutes=360,
            torbox_configured=True,
            tmdb_configured=True,
            resolver_configured=True,
            aiostreams_configured=True,
        ),
        **changes,
    )


def _settings_repository(
    snapshot: SettingsSnapshot,
    *,
    torbox_key: str | None,
    tmdb_key: str | None,
    aiostreams_url: str | None,
) -> type:
    class FakeSettingsRepository:
        def __init__(self, session: object, settings: object) -> None:
            _ = (session, settings)

        async def snapshot_with_env(self) -> SettingsSnapshot:
            return snapshot

        async def provider_api_key(self, provider: str) -> str | None:
            return torbox_key if provider == "torbox" else tmdb_key

        async def aiostreams_base_url_value(self) -> str | None:
            return aiostreams_url

    return FakeSettingsRepository


def _sync_state_repository(recorded: dict[str, object]) -> type:
    class FakeSyncStateRepository:
        def __init__(self, session: object) -> None:
            _ = session

        async def record_season_completion(self, **kwargs: object) -> int:
            recorded.update(kwargs)
            return 1

    return FakeSyncStateRepository
