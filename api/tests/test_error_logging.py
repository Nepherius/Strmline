from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.core.error_logging import (
    ERROR_LOG_FILENAME,
    ERROR_LOG_RETENTION,
    ErrorLogWriter,
    purge_expired_error_logs,
    read_recent_error_logs,
    redact_message,
)


@pytest.mark.asyncio
async def test_error_log_writer_writes_redacted_application_errors(tmp_path: Path) -> None:
    log_dir = tmp_path
    writer = ErrorLogWriter(log_dir)
    await writer.start()
    logging.getLogger("app.api.search").error("Failed with token=secret and Bearer abc.def")
    logging.getLogger("httpx").error("External client failure.")
    await writer.shutdown()

    records = read_recent_error_logs(log_dir, limit=10)

    assert len(records) == 1
    assert records[0].logger_name == "app.api.search"
    assert records[0].message == "Failed with token=[redacted] and Bearer [redacted]"
    assert (log_dir / ERROR_LOG_FILENAME).is_file()


@pytest.mark.asyncio
async def test_error_log_writer_uses_daily_utc_rotation(tmp_path: Path) -> None:
    writer = ErrorLogWriter(tmp_path)
    await writer.start()

    handler = writer._handler  # pyright: ignore[reportPrivateUsage]
    assert handler is not None
    assert handler.backupCount == 90
    assert handler.utc is True
    assert handler.when == "MIDNIGHT"

    await writer.shutdown()
    assert handler not in logging.getLogger("app").handlers


def test_purge_expired_error_logs_removes_only_old_rotations(tmp_path: Path) -> None:
    log_dir = tmp_path
    now = datetime(2026, 7, 16, tzinfo=UTC)
    old_rotation = log_dir / f"{ERROR_LOG_FILENAME}.2026-01-01"
    recent_rotation = log_dir / f"{ERROR_LOG_FILENAME}.2026-07-15"
    active_log = log_dir / ERROR_LOG_FILENAME
    for path in (old_rotation, recent_rotation, active_log):
        _ = path.write_text("", encoding="utf-8")
    old_timestamp = (now - ERROR_LOG_RETENTION - timedelta(days=1)).timestamp()
    os.utime(old_rotation, (old_timestamp, old_timestamp))

    removed = purge_expired_error_logs(log_dir, now=now)

    assert removed == 1
    assert not old_rotation.exists()
    assert recent_rotation.exists()
    assert active_log.exists()


def test_read_recent_error_logs_sorts_records_and_ignores_invalid_lines(tmp_path: Path) -> None:
    log_dir = tmp_path
    older = {
        "created_at": "2026-07-15T10:00:00+00:00",
        "logger_name": "app.sync.service",
        "message": "Older failure.",
    }
    newer = {
        "created_at": "2026-07-16T10:00:00+00:00",
        "logger_name": "app.api.search",
        "message": "Newer failure.",
    }
    _ = (log_dir / f"{ERROR_LOG_FILENAME}.2026-07-15").write_text(
        f"{json.dumps(older)}\nnot-json\n",
        encoding="utf-8",
    )
    _ = (log_dir / ERROR_LOG_FILENAME).write_text(
        f"{json.dumps(newer)}\n",
        encoding="utf-8",
    )

    records = read_recent_error_logs(log_dir, limit=1)

    assert len(records) == 1
    assert records[0].message == "Newer failure."


def test_redact_message_removes_common_secret_values() -> None:
    assert redact_message("password=hunter2 api-key=abc") == (
        "password=[redacted] api-key=[redacted]"
    )
