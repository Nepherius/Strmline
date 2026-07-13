from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.repositories.settings import AppSettingsRepository
from app.db.repositories.sync_state import SyncStateRepository
from app.db.repositories.tmdb_cache import TmdbCacheRepository
from app.providers.aiostreams.client import AioStreamsClient, AioStreamsClientError
from app.providers.tmdb.client import TmdbClient, TmdbClientError
from app.providers.tmdb.metadata import TmdbMetadataService
from app.providers.torbox.client import TorBoxAPIError, TorBoxClient
from app.providers.torbox.files import DOWNLOAD_KINDS
from app.season_completion.discovery import AioStreamsRequestLimiter, discover_candidates
from app.season_completion.inventory import (
    LibraryShow,
    SeasonInventoryRepository,
    source_filename_index,
)
from app.season_completion.matching import title_matches_show
from app.season_completion.metadata import imdb_id, regular_released_episodes, season_numbers
from app.season_completion.ranking import (
    CompletionCandidate,
    EpisodeRef,
    choose_candidates,
    dominant_release_family,
)
from app.sync.service import run_torbox_account_sync


class SeasonCompletionAlreadyRunningError(RuntimeError):
    """Raised when another season completion pass is active."""


@dataclass(frozen=True, slots=True)
class SeasonCompletionSummary:
    checked_shows: int
    missing_episodes: int
    added_torrents: int
    diagnostics: tuple[tuple[str | None, str], ...]


_COMPLETION_LOCK = asyncio.Lock()
logger = logging.getLogger(__name__)


async def run_season_completion(
    session: AsyncSession,
    settings: Settings,
) -> SeasonCompletionSummary:
    if _COMPLETION_LOCK.locked():
        raise SeasonCompletionAlreadyRunningError("Season auto-complete is already running.")
    async with _COMPLETION_LOCK:
        return await _run_season_completion(session, settings)


async def _run_season_completion(
    session: AsyncSession,
    settings: Settings,
) -> SeasonCompletionSummary:
    settings_repository = AppSettingsRepository(session, settings)
    snapshot = await settings_repository.snapshot_with_env()
    torbox_key = await settings_repository.provider_api_key("torbox")
    tmdb_key = await settings_repository.provider_api_key("tmdb")
    aiostreams_url = await settings_repository.aiostreams_base_url_value()
    missing_configuration = _missing_configuration(
        torbox_key=torbox_key,
        tmdb_key=tmdb_key,
        aiostreams_url=aiostreams_url,
    )
    if missing_configuration:
        return await _record_summary(
            session,
            SeasonCompletionSummary(0, 0, 0, ((None, missing_configuration),)),
        )
    if not snapshot.shows_enabled and not snapshot.anime_enabled:
        return await _record_summary(
            session,
            SeasonCompletionSummary(
                0,
                0,
                0,
                ((None, "Season auto-complete skipped because shows and anime are disabled."),),
            ),
        )

    torbox_key = cast(str, torbox_key)
    tmdb_key = cast(str, tmdb_key)
    aiostreams_url = cast(str, aiostreams_url)
    _ = await run_torbox_account_sync(session, settings, source="auto")

    metadata = TmdbMetadataService(
        cache_repository=TmdbCacheRepository(session),
        tmdb_client=TmdbClient(
            api_key=tmdb_key,
            base_url=settings.tmdb_base_url,
            timeout_seconds=settings.outbound_timeout_seconds,
        ),
    )
    aiostreams = AioStreamsClient(
        base_url=aiostreams_url,
        timeout_seconds=settings.outbound_timeout_seconds,
    )
    async with TorBoxClient(
        api_key=torbox_key,
        base_url=settings.torbox_base_url,
        timeout=settings.outbound_timeout_seconds,
    ) as torbox:
        downloads = {kind: await torbox.list_downloads(kind) for kind in DOWNLOAD_KINDS}
        shows = await SeasonInventoryRepository(session).shows(source_filename_index(downloads))
        missing_count, added_hashes, diagnostics = await _complete_inventory(
            shows=shows,
            metadata=metadata,
            aiostreams=aiostreams,
            torbox=torbox,
            allow_uncached=snapshot.season_auto_complete_allow_uncached,
            shows_per_minute=snapshot.season_auto_complete_shows_per_minute,
        )

    if added_hashes:
        _ = await run_torbox_account_sync(session, settings, source="auto")

    return await _record_summary(
        session,
        SeasonCompletionSummary(
            checked_shows=len(shows),
            missing_episodes=missing_count,
            added_torrents=len(added_hashes),
            diagnostics=tuple(diagnostics),
        ),
    )


async def _complete_inventory(
    *,
    shows: tuple[LibraryShow, ...],
    metadata: TmdbMetadataService,
    aiostreams: AioStreamsClient,
    torbox: TorBoxClient,
    allow_uncached: bool,
    shows_per_minute: int,
) -> tuple[int, set[str], list[tuple[str | None, str]]]:
    logger.debug(
        "Season auto-complete found %d show(s); limiting checks to %d show(s) per minute.",
        len(shows),
        shows_per_minute,
    )
    diagnostics: list[tuple[str | None, str]] = []
    missing_count = 0
    added_hashes: set[str] = set()
    request_limiter = AioStreamsRequestLimiter()
    for index, show in enumerate(shows):
        started_at = monotonic()
        logger.debug(
            "Season auto-complete checking %s with %d existing episode(s).",
            show.title,
            len(show.episodes),
        )
        try:
            show_missing, _show_added, show_unresolved = await _complete_show(
                show=show,
                metadata=metadata,
                aiostreams=aiostreams,
                torbox=torbox,
                allow_uncached=allow_uncached,
                already_added=added_hashes,
                request_limiter=request_limiter,
            )
        except (AioStreamsClientError, TmdbClientError, TorBoxAPIError) as error:
            diagnostics.append(
                (show.title, _show_diagnostic(show.title, _safe_provider_error(error)))
            )
        else:
            missing_count += show_missing
            if show_unresolved > 0:
                diagnostics.append(
                    (
                        show.title,
                        _show_diagnostic(
                            show.title,
                            f"No eligible sources were found for {show_unresolved} missing episode(s).",
                        ),
                    )
                )
            logger.debug(
                "Season auto-complete finished %s: %d missing, %d unresolved.",
                show.title,
                show_missing,
                show_unresolved,
            )
        if index < len(shows) - 1:
            await _wait_for_next_show(started_at, shows_per_minute)
    return missing_count, added_hashes, diagnostics


async def _complete_show(  # noqa: PLR0913
    *,
    show: LibraryShow,
    metadata: TmdbMetadataService,
    aiostreams: AioStreamsClient,
    torbox: TorBoxClient,
    allow_uncached: bool,
    already_added: set[str],
    request_limiter: AioStreamsRequestLimiter,
) -> tuple[int, int, int]:
    show_imdb_id, released = await _released_show_episodes(show, metadata)
    missing = frozenset(released.difference(show.episodes))
    logger.debug(
        "Season auto-complete found %d released and %d missing episode(s) for %s.",
        len(released),
        len(missing),
        show.title,
    )
    selected_count, covered = await _acquire_missing(
        show=show,
        missing=missing,
        imdb_id_value=show_imdb_id,
        aiostreams=aiostreams,
        torbox=torbox,
        allow_uncached=allow_uncached,
        already_added=already_added,
        request_limiter=request_limiter,
    )
    return len(missing), selected_count, len(missing.difference(covered))


async def _released_show_episodes(
    show: LibraryShow,
    metadata: TmdbMetadataService,
) -> tuple[str, frozenset[EpisodeRef]]:
    if show.tmdb_id is None or not show.tmdb_id.isdecimal():
        raise TmdbClientError("The library item has no usable TMDB identity.")
    tmdb_id = int(show.tmdb_id)
    details = await metadata.get_season_completion_json(f"/tv/{tmdb_id}")
    external_ids = await metadata.get_season_completion_json(f"/tv/{tmdb_id}/external_ids")
    show_imdb_id = imdb_id(external_ids)
    if show_imdb_id is None:
        raise TmdbClientError("TMDB did not provide an IMDB identity for this show.")

    released: set[EpisodeRef] = set()
    for season in season_numbers(details):
        season_payload = await metadata.get_season_completion_json(f"/tv/{tmdb_id}/season/{season}")
        released.update(regular_released_episodes(season_payload, today=datetime.now(UTC).date()))
    return show_imdb_id, frozenset(released)


async def _acquire_missing(  # noqa: PLR0913
    *,
    show: LibraryShow,
    missing: frozenset[EpisodeRef],
    imdb_id_value: str,
    aiostreams: AioStreamsClient,
    torbox: TorBoxClient,
    allow_uncached: bool,
    already_added: set[str],
    request_limiter: AioStreamsRequestLimiter,
) -> tuple[int, frozenset[EpisodeRef]]:
    all_filenames = [
        filename for filenames in show.filenames_by_season.values() for filename in filenames
    ]
    selected_count = 0
    covered: set[EpisodeRef] = set()
    for season in sorted({episode.season for episode in missing}):
        season_missing = frozenset(episode for episode in missing if episode.season == season)
        logger.debug(
            "Season auto-complete searching AIOStreams for %s season %d (%d missing episode(s)).",
            show.title,
            season,
            len(season_missing),
        )
        candidates = await discover_candidates(
            aiostreams_client=aiostreams,
            torbox_client=torbox,
            imdb_id=imdb_id_value,
            missing=season_missing,
            limiter=request_limiter,
        )
        logger.debug(
            "Season auto-complete searched %s season %d: %d candidate(s).",
            show.title,
            season,
            len(candidates),
        )
        matching_candidates = [
            candidate
            for candidate in candidates
            if any(
                title_matches_show(show.title, label)
                for label in candidate.match_labels or (candidate.title,)
            )
        ]
        rejected_candidates = len(candidates) - len(matching_candidates)
        if rejected_candidates:
            logger.debug(
                "Season auto-complete rejected %d title-mismatched candidate(s) for %s season %d.",
                rejected_candidates,
                show.title,
                season,
            )
        family = dominant_release_family(list(show.filenames_by_season.get(season, ())))
        if family is None:
            family = dominant_release_family(all_filenames)
        selected = choose_candidates(
            matching_candidates,
            missing=season_missing,
            dominant_family=family,
            allow_uncached=allow_uncached,
        )
        logger.debug(
            "Season auto-complete selected %d source(s) for %s season %d.",
            len(selected),
            show.title,
            season,
        )
        for candidate in selected:
            covered.update(candidate.episodes.intersection(season_missing))
            if candidate.source_id in already_added:
                continue
            await _add_candidate(
                candidate=candidate,
                aiostreams=aiostreams,
                torbox=torbox,
            )
            already_added.add(candidate.source_id)
            selected_count += 1
    return selected_count, frozenset(covered)


async def _add_candidate(
    *,
    candidate: CompletionCandidate,
    aiostreams: AioStreamsClient,
    torbox: TorBoxClient,
) -> None:
    if candidate.action_url is not None:
        _ = await aiostreams.trigger_stream_url(candidate.action_url)
        return
    if candidate.info_hash is None:
        return
    try:
        _ = await torbox.create_torrent(
            magnet=f"magnet:?xt=urn:btih:{candidate.info_hash}",
            name=candidate.title,
            add_only_if_cached=candidate.cached,
        )
    except TorBoxAPIError as error:
        if error.error_code != "DUPLICATE_ITEM":
            raise


async def _record_summary(
    session: AsyncSession,
    summary: SeasonCompletionSummary,
) -> SeasonCompletionSummary:
    _ = await SyncStateRepository(session).record_season_completion(
        checked_shows=summary.checked_shows,
        missing_episodes=summary.missing_episodes,
        added_torrents=summary.added_torrents,
        diagnostics=summary.diagnostics,
    )
    return summary


def _missing_configuration(
    *,
    torbox_key: str | None,
    tmdb_key: str | None,
    aiostreams_url: str | None,
) -> str | None:
    missing = [
        label
        for value, label in (
            (torbox_key, "TorBox"),
            (tmdb_key, "TMDB"),
            (aiostreams_url, "AIOStreams"),
        )
        if value is None
    ]
    if not missing:
        return None
    return f"Season auto-complete requires configured {', '.join(missing)} providers."


def _safe_provider_error(error: Exception) -> str:
    if isinstance(error, TmdbClientError):
        return str(error) or "TMDB lookup failed."
    if isinstance(error, AioStreamsClientError):
        return "AIOStreams episode lookup failed."
    return "TorBox season acquisition failed."


async def _wait_for_next_show(started_at: float, shows_per_minute: int) -> None:
    interval = 60 / shows_per_minute
    delay = interval - (monotonic() - started_at)
    if delay <= 0:
        return
    logger.debug("Season auto-complete rate limit waiting %.1f seconds.", delay)
    await asyncio.sleep(delay)


def _show_diagnostic(title: str, message: str) -> str:
    return f"{title}: {message}"
