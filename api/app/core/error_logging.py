"""Persist sanitized application errors in discoverable rotating files."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import override

ERROR_LOG_RETENTION = timedelta(days=90)
RETENTION_CHECK_INTERVAL_SECONDS = 24 * 60 * 60
ERROR_LOG_FILENAME = "strmline-errors.log"
ERROR_LOG_FORMAT_VERSION = 1


@dataclass(frozen=True, slots=True)
class ErrorLogEvent:
    created_at: datetime
    logger_name: str
    message: str


class SanitizedErrorFormatter(logging.Formatter):
    @override
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "version": ERROR_LOG_FORMAT_VERSION,
                "created_at": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "logger_name": record.name[:200],
                "message": redact_message(record.getMessage()),
            },
            ensure_ascii=False,
        )


class ApplicationErrorFilter(logging.Filter):
    @override
    def filter(self, record: logging.LogRecord) -> bool:
        return record.name == "app" or record.name.startswith("app.")


class ErrorLogWriter:
    def __init__(self, log_dir: Path) -> None:
        self._log_dir = log_dir
        self._handler: TimedRotatingFileHandler | None = None
        self._retention_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        _ = purge_expired_error_logs(self._log_dir)
        handler = TimedRotatingFileHandler(
            self._log_dir / ERROR_LOG_FILENAME,
            when="midnight",
            interval=1,
            backupCount=90,
            encoding="utf-8",
            delay=False,
            utc=True,
        )
        handler.setLevel(logging.ERROR)
        handler.setFormatter(SanitizedErrorFormatter())
        handler.addFilter(ApplicationErrorFilter())
        logging.getLogger("app").addHandler(handler)
        self._handler = handler
        self._retention_task = asyncio.create_task(self._purge_expired_events())

    async def shutdown(self) -> None:
        if self._handler is not None:
            logging.getLogger("app").removeHandler(self._handler)
            self._handler.close()
            self._handler = None
        await _cancel_task(self._retention_task)

    async def _purge_expired_events(self) -> None:
        while True:
            await asyncio.sleep(RETENTION_CHECK_INTERVAL_SECONDS)
            _ = purge_expired_error_logs(self._log_dir)


def purge_expired_error_logs(log_dir: Path, *, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(UTC)) - ERROR_LOG_RETENTION
    removed = 0
    for path in log_dir.glob(f"{ERROR_LOG_FILENAME}.*"):
        try:
            modified_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            if modified_at < cutoff:
                path.unlink()
                removed += 1
        except FileNotFoundError:
            continue
    return removed


def read_recent_error_logs(log_dir: Path, *, limit: int) -> tuple[ErrorLogEvent, ...]:
    events: list[ErrorLogEvent] = []
    for path in log_dir.glob(f"{ERROR_LOG_FILENAME}*"):
        if not path.is_file():
            continue
        try:
            with path.open(encoding="utf-8") as log_file:
                for line in log_file:
                    event = _error_log_event(line)
                    if event is not None:
                        events.append(event)
        except OSError:
            continue
    events.sort(key=lambda event: event.created_at, reverse=True)
    return tuple(events[:limit])


def _error_log_event(line: str) -> ErrorLogEvent | None:
    try:
        payload = json.loads(line)
        created_at = datetime.fromisoformat(payload["created_at"])
        logger_name = payload["logger_name"]
        message = payload["message"]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    if not isinstance(logger_name, str) or not isinstance(message, str):
        return None
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return ErrorLogEvent(
        created_at=created_at,
        logger_name=logger_name,
        message=message,
    )


async def _cancel_task(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    _ = task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def redact_message(message: str) -> str:
    without_bearer = re.sub(r"(?i)bearer\s+[^\s]+", "Bearer [redacted]", message)
    return re.sub(
        r"(?i)(api[_-]?key|password|token)=([^\s&]+)",
        r"\1=[redacted]",
        without_bearer,
    )
