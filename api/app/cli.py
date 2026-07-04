from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.db.repositories.sync_state import SyncStateRepository
from app.db.session import build_session_factory
from app.library.strm_probe import StrmProbeError, probe_strm_file
from app.providers.torbox.client import TorBoxAPIError, TorBoxClient
from app.providers.torbox.files import DOWNLOAD_KINDS, DownloadKind
from app.sync.torbox_strm import DirectTorBoxStrmSync, ResolverUrlConfig, TorBoxStrmSyncResult


@dataclass(frozen=True, slots=True)
class SyncTorBoxStrmOptions:
    allow_direct_urls: bool
    library_root: Path | None
    resolver_base_url: str | None
    resolver_token: str | None
    kinds: tuple[DownloadKind, ...]
    max_files: int | None
    probe_first_url: bool


@dataclass(frozen=True, slots=True)
class SyncTorBoxStrmContext:
    output_root: Path
    resolver: ResolverUrlConfig | None
    api_key: str


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "sync-torbox-strm":
        kinds = tuple(args.kinds) if args.kinds else DOWNLOAD_KINDS
        return asyncio.run(
            _sync_torbox_strm(
                SyncTorBoxStrmOptions(
                    allow_direct_urls=args.allow_direct_urls,
                    library_root=args.library_root,
                    resolver_base_url=args.resolver_base_url,
                    resolver_token=args.resolver_token,
                    kinds=cast(tuple[DownloadKind, ...], kinds),
                    max_files=args.max_files,
                    probe_first_url=args.probe_first_url,
                )
            )
        )
    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="strmline")
    subparsers = parser.add_subparsers(dest="command")
    sync_parser = subparsers.add_parser(
        "sync-torbox-strm",
        help="Generate .strm files from cached TorBox account media.",
    )
    _ = sync_parser.add_argument(
        "--direct-torbox-urls",
        dest="allow_direct_urls",
        action="store_true",
        help="Write TorBox request-download URLs directly into .strm files for local testing.",
    )
    _ = sync_parser.add_argument(
        "--resolver-base-url",
        default=None,
        help="Base URL used for generated resolver .strm files. Overrides STRMLINE_BASE_URL.",
    )
    _ = sync_parser.add_argument(
        "--resolver-token",
        default=None,
        help="Resolver token used in generated .strm files. Overrides STRMLINE_RESOLVER_TOKEN.",
    )
    _ = sync_parser.add_argument(
        "--library-root",
        type=Path,
        default=None,
        help="Generated library output folder. Overrides STRMLINE_LIBRARY_ROOT.",
    )
    _ = sync_parser.add_argument(
        "--kind",
        action="append",
        choices=DOWNLOAD_KINDS,
        dest="kinds",
        help="TorBox download kind to sync. Repeat to include multiple kinds.",
    )
    _ = sync_parser.add_argument(
        "--max-files",
        type=positive_int,
        default=None,
        help="Maximum number of .strm files to write for a smoke test.",
    )
    _ = sync_parser.add_argument(
        "--probe-first-url",
        action="store_true",
        help="Probe the first generated .strm URL without following or printing redirects.",
    )
    return parser


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        msg = "value must be positive"
        raise ValueError(msg)
    return parsed


async def _sync_torbox_strm(options: SyncTorBoxStrmOptions) -> int:
    settings = get_settings()
    context = _sync_context(options, settings)
    if isinstance(context, str):
        _write_error(context)
        return 2

    result = await _run_sync(options, settings, context)
    if result is None:
        return 1

    sync_run_id = await _database_sync_run_id(settings.database_url, result, context.output_root)
    if isinstance(sync_run_id, str):
        _write_error(sync_run_id)
        return 1

    lines = _sync_summary_lines(
        kinds=options.kinds,
        max_files=options.max_files,
        output_root=context.output_root,
        result=result,
        resolver_enabled=context.resolver is not None,
        sync_run_id=sync_run_id,
    )
    if options.probe_first_url and result.written_paths:
        probe_line = await _probe_summary_line(
            result.written_paths[0],
            request_timeout=settings.outbound_timeout_seconds,
        )
        if probe_line is None:
            return 1
        lines.append(probe_line)
    _write_output("\n".join(lines) + "\n")
    return 0


def _sync_context(
    options: SyncTorBoxStrmOptions,
    settings: Settings,
) -> SyncTorBoxStrmContext | str:
    if settings.torbox_api_key is None:
        return "STRMLINE_TORBOX_API_KEY is required."
    output_root = _output_root(options.library_root, settings.library_root)
    if output_root is None:
        return "STRMLINE_LIBRARY_ROOT or --library-root is required."
    resolver = _resolver_config(
        allow_direct_urls=options.allow_direct_urls,
        resolver_base_url=options.resolver_base_url,
        resolver_token=options.resolver_token,
        settings_base_url=settings.base_url,
        settings_resolver_token=(
            settings.resolver_token.get_secret_value()
            if settings.resolver_token is not None
            else None
        ),
    )
    if resolver is None and not options.allow_direct_urls:
        return " ".join(
            (
                "Resolver mode requires STRMLINE_BASE_URL and STRMLINE_RESOLVER_TOKEN",
                "or --resolver-base-url and --resolver-token.",
            )
        )
    return SyncTorBoxStrmContext(
        output_root=output_root,
        resolver=resolver,
        api_key=settings.torbox_api_key.get_secret_value(),
    )


async def _run_sync(
    options: SyncTorBoxStrmOptions,
    settings: Settings,
    context: SyncTorBoxStrmContext,
) -> TorBoxStrmSyncResult | None:
    try:
        async with TorBoxClient(
            api_key=context.api_key,
            base_url=settings.torbox_base_url,
            timeout=settings.outbound_timeout_seconds,
        ) as client:
            sync = DirectTorBoxStrmSync(
                client=client,
                api_key=context.api_key,
                torbox_base_url=settings.torbox_base_url,
                library_root=context.output_root,
                resolver=context.resolver,
            )
            return await sync.run(kinds=options.kinds, max_files=options.max_files)
    except (OSError, TorBoxAPIError, ValueError) as error:
        _write_error(f"TorBox STRM sync failed: {error}")
        return None


async def _database_sync_run_id(
    database_url: str | None,
    result: TorBoxStrmSyncResult,
    output_root: Path,
) -> int | str | None:
    if database_url is None:
        return None
    try:
        return await _persist_sync_result(result, output_root, database_url)
    except SQLAlchemyError as error:
        return f"TorBox STRM sync state persistence failed: {error}"


def _output_root(override: Path | None, configured: Path | None) -> Path | None:
    return override or configured


def _resolver_config(
    *,
    allow_direct_urls: bool,
    resolver_base_url: str | None,
    resolver_token: str | None,
    settings_base_url: str | None,
    settings_resolver_token: str | None,
) -> ResolverUrlConfig | None:
    if allow_direct_urls:
        return None
    base_url = resolver_base_url or settings_base_url
    token = resolver_token or settings_resolver_token
    if base_url is None or token is None:
        return None
    return ResolverUrlConfig(base_url=base_url, token=token)


def _sync_summary_lines(
    *,
    kinds: tuple[DownloadKind, ...],
    max_files: int | None,
    output_root: Path,
    result: TorBoxStrmSyncResult,
    resolver_enabled: bool,
    sync_run_id: int | None,
) -> list[str]:
    lines = [
        "TorBox STRM sync complete.",
        f"Playback mode: {'resolver' if resolver_enabled else 'direct TorBox URLs'}",
        f"Synced kinds: {', '.join(kinds)}",
        f"Scanned video files: {result.scanned_files}",
        f"Written STRM files: {result.written_files}",
        f"Skipped items/files: {result.skipped_files}",
        f"Library root: {output_root}",
        f"Movies folder: {output_root / 'movies'}",
        f"Shows folder: {output_root / 'shows'}",
        f"Anime folder: {output_root / 'anime'}",
    ]
    if max_files is not None:
        lines.append(f"Smoke-test file cap: {max_files}")
    if result.manifest_path is not None:
        lines.append(f"Resolver manifest: {result.manifest_path}")
    if sync_run_id is not None:
        lines.append(f"Database sync run ID: {sync_run_id}")
    if not result.written_paths:
        lines.append("No .strm files were written from the selected TorBox content.")
        return lines

    lines.append("Sample STRM files:")
    lines.extend(f"- {path}" for path in result.written_paths[:5])
    return lines


async def _probe_summary_line(path: Path, *, request_timeout: float) -> str | None:
    try:
        probe_result = await probe_strm_file(path, request_timeout=request_timeout)
    except StrmProbeError as error:
        _write_error(f"First STRM URL probe failed: {error}")
        return None
    response_kind = "redirect" if probe_result.redirected else "direct response"
    return f"First STRM URL probe: status {probe_result.status_code} ({response_kind})."


async def _persist_sync_result(
    result: TorBoxStrmSyncResult,
    output_root: Path,
    database_url: str,
) -> int:
    session_factory = build_session_factory(database_url)
    async with session_factory() as session:
        return await SyncStateRepository(session).record_success(result, output_root)


def _write_output(message: str) -> None:
    _ = sys.stdout.write(message)


def _write_error(message: str) -> None:
    _ = sys.stderr.write(f"{message}\n")


if __name__ == "__main__":
    raise SystemExit(main())
