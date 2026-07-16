from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from app.db.repositories.stream_selection import (
    StreamSelectionRecord,
    StreamSelectionRepository,
    StreamSelectionWrite,
)
from app.providers.aiostreams.client import (
    AioStreamsClient,
    AioStreamsClientError,
    AioStreamsStream,
)
from app.providers.torbox.client import TorBoxAPIError, TorBoxClient
from app.providers.torbox.files import torrent_info_hash
from app.search.stream_identity import (
    find_stream_by_key,
    stream_display_name,
    stream_identity,
)


class StreamActionError(RuntimeError):
    """Raised when a selected stream cannot be added or removed safely."""


@dataclass(frozen=True, slots=True)
class StreamActionTarget:
    media_type: str
    media_id: str
    stream_key: str
    tmdb_id: str | None = None
    media_title: str | None = None
    media_year: int | None = None
    media_poster_path: str | None = None


@dataclass(frozen=True, slots=True)
class StreamActionOutcome:
    stream_key: str
    selected: bool
    torbox_torrent_id: str | None
    message: str


@dataclass(frozen=True, slots=True)
class _TorrentReference:
    torrent_id: str
    info_hash: str | None


async def add_stream_to_torbox(
    *,
    aiostreams_client: AioStreamsClient,
    torbox_client: TorBoxClient,
    repository: StreamSelectionRepository,
    target: StreamActionTarget,
    add_only_if_cached: bool = True,
) -> StreamActionOutcome:
    stream = await _selected_aiostreams_stream(aiostreams_client, target)
    identity = stream_identity(stream, media_type=target.media_type, media_id=target.media_id)
    if not identity.addable:
        msg = "This stream cannot be added because it does not expose a TorBox action."
        raise StreamActionError(msg)

    if identity.magnet is not None and identity.info_hash is not None:
        torrent_id = await _create_or_find_torrent(
            torbox_client=torbox_client,
            magnet=identity.magnet,
            info_hash=identity.info_hash,
            name=stream_display_name(stream),
            add_only_if_cached=add_only_if_cached,
        )
        info_hash = identity.info_hash
        message = "Added to TorBox and saved in Strmline."
    elif identity.action_url is not None:
        torrent = await _trigger_aiostreams_torbox_action(
            aiostreams_client=aiostreams_client,
            torbox_client=torbox_client,
            stream=stream,
            action_url=identity.action_url,
        )
        if torrent is None:
            msg = "TorBox did not confirm that this stream was added. Try another result."
            raise StreamActionError(msg)
        torrent_id = torrent.torrent_id
        info_hash = torrent.info_hash
        message = "AIOStreams add triggered and saved in Strmline."
    else:
        msg = "This stream cannot be added because it does not expose a TorBox action."
        raise StreamActionError(msg)

    record = await repository.upsert(
        StreamSelectionWrite(
            stream_key=identity.stream_key,
            media_type=target.media_type,
            media_id=target.media_id,
            title=stream_display_name(stream),
            source_name=stream.name,
            info_hash=info_hash,
            torbox_torrent_id=torrent_id,
            tmdb_id=target.tmdb_id,
            media_title=target.media_title,
            media_year=target.media_year,
            media_poster_path=target.media_poster_path,
        )
    )
    return StreamActionOutcome(
        stream_key=record.stream_key,
        selected=True,
        torbox_torrent_id=record.torbox_torrent_id,
        message=message,
    )


async def remove_stream_from_torbox(
    *,
    torbox_client: TorBoxClient,
    repository: StreamSelectionRepository,
    stream_key: str,
) -> StreamActionOutcome:
    record = await repository.get(stream_key)
    if record is None:
        return StreamActionOutcome(
            stream_key=stream_key,
            selected=False,
            torbox_torrent_id=None,
            message="Removed from Strmline.",
        )

    message = "Removed from TorBox and Strmline."
    if record.torbox_torrent_id is not None:
        try:
            await torbox_client.delete_torrent(record.torbox_torrent_id)
        except TorBoxAPIError as error:
            if error.error_code == "ITEM_NOT_FOUND":
                message = "Removed from Strmline; torrent was already absent from TorBox."
            else:
                # Local removal is the user's requested operation. A stale TorBox ID,
                # provider outage, or expired credential must not leave the selection
                # (and its permanent-library retention marker) stuck in Strmline.
                message = "Removed from Strmline, but TorBox removal could not be confirmed."

    _ = await repository.delete(stream_key)
    return StreamActionOutcome(
        stream_key=stream_key,
        selected=False,
        torbox_torrent_id=None,
        message=message,
    )


async def ensure_selected_streams_in_torbox(
    *,
    torbox_client: TorBoxClient,
    repository: StreamSelectionRepository,
    aiostreams_client: AioStreamsClient | None = None,
) -> None:
    selections = await repository.list_selected()
    existing_by_hash = await torbox_client.find_torrents_by_hashes(
        {selection.info_hash for selection in selections if selection.info_hash is not None}
    )
    for selection in selections:
        if selection.info_hash is None:
            if selection.torbox_torrent_id is None and aiostreams_client is not None:
                await _trigger_saved_aiostreams_action(
                    aiostreams_client=aiostreams_client,
                    torbox_client=torbox_client,
                    repository=repository,
                    selection=selection,
                )
            continue
        existing = existing_by_hash.get(selection.info_hash.casefold())
        if existing is not None:
            await repository.update_torbox_id(selection.stream_key, _torrent_id(existing))
            continue
        try:
            data = await torbox_client.create_torrent(
                magnet=f"magnet:?xt=urn:btih:{selection.info_hash}",
                name=selection.title,
                add_only_if_cached=True,
            )
        except TorBoxAPIError as error:
            if error.error_code != "DUPLICATE_ITEM":
                continue
            existing = await torbox_client.find_torrent_by_hash(selection.info_hash)
            await repository.update_torbox_id(selection.stream_key, _torrent_id(existing))
            continue
        await repository.update_torbox_id(selection.stream_key, _torrent_id(data))


async def _trigger_saved_aiostreams_action(
    *,
    aiostreams_client: AioStreamsClient,
    torbox_client: TorBoxClient,
    repository: StreamSelectionRepository,
    selection: StreamSelectionRecord,
) -> None:
    target = StreamActionTarget(
        media_type=selection.media_type,
        media_id=selection.media_id,
        stream_key=selection.stream_key,
    )
    try:
        stream = await _selected_aiostreams_stream(aiostreams_client, target)
        identity = stream_identity(
            stream,
            media_type=selection.media_type,
            media_id=selection.media_id,
        )
        if identity.action_url is None:
            return
        torrent = await _trigger_aiostreams_torbox_action(
            aiostreams_client=aiostreams_client,
            torbox_client=torbox_client,
            stream=stream,
            action_url=identity.action_url,
        )
    except (AioStreamsClientError, StreamActionError, TorBoxAPIError):
        return
    if torrent is None:
        return
    await repository.update_torbox_identity(
        selection.stream_key,
        torbox_torrent_id=torrent.torrent_id,
        info_hash=torrent.info_hash,
    )


async def _selected_aiostreams_stream(
    aiostreams_client: AioStreamsClient,
    target: StreamActionTarget,
) -> AioStreamsStream:
    stremio_type = "movie" if target.media_type == "movie" else "series"
    streams = await aiostreams_client.streams(
        media_type=stremio_type,
        media_id=target.media_id,
    )
    stream = find_stream_by_key(
        streams,
        media_type=target.media_type,
        media_id=target.media_id,
        stream_key=target.stream_key,
    )
    if stream is None:
        msg = "This stream result is no longer available. Refresh the search and try again."
        raise StreamActionError(msg)
    return stream


async def _create_or_find_torrent(
    *,
    torbox_client: TorBoxClient,
    magnet: str,
    info_hash: str,
    name: str,
    add_only_if_cached: bool,
) -> str | None:
    try:
        data = await torbox_client.create_torrent(
            magnet=magnet,
            name=name,
            add_only_if_cached=add_only_if_cached,
        )
    except TorBoxAPIError as error:
        if error.error_code != "DUPLICATE_ITEM":
            raise
        existing = await torbox_client.find_torrent_by_hash(info_hash)
        return _torrent_id(existing)
    return _torrent_id(data)


async def _trigger_aiostreams_torbox_action(
    *,
    aiostreams_client: AioStreamsClient,
    torbox_client: TorBoxClient,
    stream: AioStreamsStream,
    action_url: str,
) -> _TorrentReference | None:
    before_ids = _download_ids(await torbox_client.list_downloads("torrents"))
    _ = await aiostreams_client.trigger_stream_url(action_url)
    after_downloads = await torbox_client.list_downloads("torrents")
    new_downloads = [
        download for download in after_downloads if _torrent_id(download) not in before_ids
    ]
    matched = (
        _matching_download(stream, new_downloads)
        or _matching_download(stream, after_downloads)
        or (new_downloads[0] if len(new_downloads) == 1 else None)
    )
    return _torrent_reference(matched)


def _download_ids(downloads: list[dict[str, Any]]) -> set[str]:
    return {
        torrent_id for download in downloads if (torrent_id := _torrent_id(download)) is not None
    }


def _matching_download(
    stream: AioStreamsStream,
    downloads: list[dict[str, Any]],
) -> dict[str, Any] | None:
    filename = stream.behavior_hints.get("filename")
    expected_names = {
        value.strip().casefold()
        for value in (filename, stream.title)
        if isinstance(value, str) and value.strip()
    }
    expected_size = stream.behavior_hints.get("videoSize")
    for download in downloads:
        if _download_matches(download, expected_names, expected_size):
            return download
    return None


def _download_matches(
    download: dict[str, Any],
    expected_names: set[str],
    expected_size: object,
) -> bool:
    download_name = download.get("name")
    if isinstance(download_name, str) and download_name.strip().casefold() in expected_names:
        return True
    files = download.get("files")
    if not isinstance(files, list):
        return False
    for raw_file in cast(list[object], files):
        if not isinstance(raw_file, dict):
            continue
        file_data = cast(dict[str, Any], raw_file)
        name = file_data.get("name") or file_data.get("short_name") or file_data.get("filename")
        size = file_data.get("size")
        name_matches = isinstance(name, str) and any(
            name.casefold().endswith(expected_name) for expected_name in expected_names
        )
        size_matches = isinstance(expected_size, int) and size == expected_size
        if name_matches or size_matches:
            return True
    return False


def _torrent_id(payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return None
    torrent_id = payload.get("torrent_id") or payload.get("id")
    if isinstance(torrent_id, int):
        return str(torrent_id)
    if isinstance(torrent_id, str) and torrent_id.strip():
        return torrent_id.strip()
    return None


def _torrent_reference(payload: dict[str, Any] | None) -> _TorrentReference | None:
    torrent_id = _torrent_id(payload)
    if torrent_id is None or payload is None:
        return None
    return _TorrentReference(
        torrent_id=torrent_id,
        info_hash=torrent_info_hash(payload),
    )
