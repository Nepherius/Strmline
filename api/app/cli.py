from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from app.core.config import get_settings
from app.library.strm_probe import StrmProbeError, probe_strm_file
from app.providers.torbox.client import TorBoxAPIError, TorBoxClient
from app.providers.torbox.files import DOWNLOAD_KINDS, DownloadKind
from app.sync.torbox_strm import DirectTorBoxStrmSync, TorBoxStrmSyncResult


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "sync-torbox-strm":
        kinds = tuple(args.kinds) if args.kinds else DOWNLOAD_KINDS
        return asyncio.run(
            _sync_torbox_strm(
                allow_direct_urls=args.allow_direct_urls,
                library_root=args.library_root,
                kinds=cast(tuple[DownloadKind, ...], kinds),
                max_files=args.max_files,
                probe_first_url=args.probe_first_url,
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


async def _sync_torbox_strm(
    *,
    allow_direct_urls: bool,
    library_root: Path | None,
    kinds: tuple[DownloadKind, ...],
    max_files: int | None,
    probe_first_url: bool,
) -> int:
    if not allow_direct_urls:
        message = " ".join(
            (
                "Direct TorBox URL generation must be explicit.",
                "Re-run with --direct-torbox-urls for the current local test mode.",
            )
        )
        _write_error(message)
        return 2

    settings = get_settings()
    if settings.torbox_api_key is None:
        _write_error("STRMLINE_TORBOX_API_KEY is required.")
        return 2
    output_root = _output_root(library_root, settings.library_root)
    if output_root is None:
        _write_error("STRMLINE_LIBRARY_ROOT or --library-root is required.")
        return 2

    api_key = settings.torbox_api_key.get_secret_value()
    try:
        async with TorBoxClient(
            api_key=api_key,
            base_url=settings.torbox_base_url,
            timeout=settings.outbound_timeout_seconds,
        ) as client:
            sync = DirectTorBoxStrmSync(
                client=client,
                api_key=api_key,
                torbox_base_url=settings.torbox_base_url,
                library_root=output_root,
            )
            result = await sync.run(kinds=kinds, max_files=max_files)
    except (OSError, TorBoxAPIError, ValueError) as error:
        _write_error(f"TorBox STRM sync failed: {error}")
        return 1

    lines = _sync_summary_lines(
        kinds=kinds,
        max_files=max_files,
        output_root=output_root,
        result=result,
    )
    if probe_first_url and result.written_paths:
        probe_line = await _probe_summary_line(
            result.written_paths[0],
            request_timeout=settings.outbound_timeout_seconds,
        )
        if probe_line is None:
            return 1
        lines.append(probe_line)
    _write_output("\n".join(lines) + "\n")
    return 0


def _output_root(override: Path | None, configured: Path | None) -> Path | None:
    return override or configured


def _sync_summary_lines(
    *,
    kinds: tuple[DownloadKind, ...],
    max_files: int | None,
    output_root: Path,
    result: TorBoxStrmSyncResult,
) -> list[str]:
    lines = [
        "TorBox STRM sync complete.",
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


def _write_output(message: str) -> None:
    _ = sys.stdout.write(message)


def _write_error(message: str) -> None:
    _ = sys.stderr.write(f"{message}\n")


if __name__ == "__main__":
    raise SystemExit(main())
