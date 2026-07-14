"""Persist sanitized application errors without delaying request handling."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import override

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.error_log import ErrorLogRepository

ERROR_LOG_RETENTION = timedelta(days=90)
RETENTION_CHECK_INTERVAL_SECONDS = 24 * 60 * 60
MAX_PENDING_ERROR_LOGS = 1_000

AsyncSessionFactory = Callable[[], AsyncSession]


@dataclass(frozen=True, slots=True)
class ErrorLogEvent:
    logger_name: str
    message: str


class DatabaseErrorLogHandler(logging.Handler):
    def __init__(self, queue: asyncio.Queue[ErrorLogEvent]) -> None:
        super().__init__(level=logging.ERROR)
        self._queue = queue

    @override
    def emit(self, record: logging.LogRecord) -> None:
        if not record.name.startswith("app"):
            return
        event = ErrorLogEvent(
            logger_name=record.name[:200],
            message=redact_message(record.getMessage()),
        )
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            return


class ErrorLogWriter:
    def __init__(self, session_factory: AsyncSessionFactory) -> None:
        self._session_factory = session_factory
        self._queue: asyncio.Queue[ErrorLogEvent] = asyncio.Queue(MAX_PENDING_ERROR_LOGS)
        self._handler = DatabaseErrorLogHandler(self._queue)
        self._writer_task: asyncio.Task[None] | None = None
        self._retention_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        logging.getLogger("app").addHandler(self._handler)
        self._writer_task = asyncio.create_task(self._write_events())
        self._retention_task = asyncio.create_task(self._purge_expired_events())

    async def shutdown(self) -> None:
        logging.getLogger("app").removeHandler(self._handler)
        await self._queue.join()
        await _cancel_task(self._writer_task)
        await _cancel_task(self._retention_task)

    async def _write_events(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                async with self._session_factory() as session:
                    await ErrorLogRepository(session).record(
                        logger_name=event.logger_name,
                        message=event.message,
                    )
            except (OSError, SQLAlchemyError):
                # Logging failures must not recursively log through this handler.
                continue
            finally:
                self._queue.task_done()

    async def _purge_expired_events(self) -> None:
        while True:
            try:
                async with self._session_factory() as session:
                    await ErrorLogRepository(session).purge_before(
                        datetime.now(UTC) - ERROR_LOG_RETENTION
                    )
            except (OSError, SQLAlchemyError) as error:
                _ = error
            await asyncio.sleep(RETENTION_CHECK_INTERVAL_SECONDS)


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
