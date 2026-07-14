from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_logging import (
    AsyncSessionFactory,
    DatabaseErrorLogHandler,
    ErrorLogEvent,
    ErrorLogWriter,
    redact_message,
)
from app.db.models import ErrorLog
from app.db.repositories.error_log import ErrorLogRepository


class FakeResult:
    def __init__(self, scalars: list[object] | None = None) -> None:
        self._scalars = scalars or []

    def scalars(self) -> list[object]:
        return self._scalars


class FakeSession:
    def __init__(self, results: list[FakeResult] | None = None) -> None:
        self._results = results or []
        self.added: list[object] = []
        self.committed = False

    async def execute(self, statement: object) -> FakeResult:
        _ = statement
        return self._results.pop(0) if self._results else FakeResult()

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def commit(self) -> None:
        self.committed = True


@pytest.mark.asyncio
async def test_error_log_repository_records_and_purges_error_records() -> None:
    session = FakeSession([FakeResult(), FakeResult()])
    repository = ErrorLogRepository(cast(AsyncSession, session))

    await repository.record(logger_name="app.main", message="Request failed.")
    await repository.purge_before(datetime.now(UTC) - timedelta(days=90))

    assert session.committed is True
    error_log = cast(ErrorLog, session.added[0])
    assert error_log.logger_name == "app.main"
    assert error_log.message == "Request failed."


def test_error_log_handler_queues_redacted_error_messages() -> None:
    queue: asyncio.Queue[ErrorLogEvent] = asyncio.Queue()
    handler = DatabaseErrorLogHandler(queue)
    record = logging.LogRecord(
        name="app.api.search",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="Failed with token=secret and Bearer abc.def",
        args=(),
        exc_info=None,
    )

    handler.emit(record)

    event = queue.get_nowait()
    assert event.logger_name == "app.api.search"
    assert event.message == "Failed with token=[redacted] and Bearer [redacted]"


def test_error_log_handler_ignores_non_application_logs() -> None:
    queue: asyncio.Queue[ErrorLogEvent] = asyncio.Queue()
    handler = DatabaseErrorLogHandler(queue)
    record = logging.LogRecord(
        name="httpx",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="Request failed.",
        args=(),
        exc_info=None,
    )

    handler.emit(record)

    assert queue.empty()


def test_redact_message_removes_common_secret_values() -> None:
    assert redact_message("password=hunter2 api-key=abc") == (
        "password=[redacted] api-key=[redacted]"
    )


@pytest.mark.asyncio
async def test_error_log_writer_removes_handler_on_shutdown() -> None:
    class FakeSessionContext:
        async def __aenter__(self) -> FakeSession:
            return FakeSession()

        async def __aexit__(self, *args: object) -> None:
            _ = args

    def session_factory() -> FakeSessionContext:
        return FakeSessionContext()

    writer = ErrorLogWriter(cast(AsyncSessionFactory, session_factory))
    await writer.start()
    await writer.shutdown()

    assert writer._handler not in logging.getLogger("app").handlers  # pyright: ignore[reportPrivateUsage]
