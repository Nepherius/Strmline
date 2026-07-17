import logging
from typing import override

import httpx
import pytest

from app.core.config import get_settings
from app.core.logging import configure_debug_logging
from app.main import create_app


def test_debug_logging_changes_app_log_level() -> None:
    configure_debug_logging(enabled=True)
    assert logging.getLogger("app").getEffectiveLevel() == logging.DEBUG
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING

    configure_debug_logging(enabled=False)
    assert logging.getLogger("app").getEffectiveLevel() == logging.INFO


def test_legacy_debug_logging_environment_variable_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRMLINE_DEBUG_LOGGING", "true")
    get_settings.cache_clear()

    _ = create_app()

    assert logging.getLogger("app").getEffectiveLevel() == logging.INFO
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_debug_logging_includes_request_summary() -> None:
    records: list[logging.LogRecord] = []

    class RecordingHandler(logging.Handler):
        @override
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = RecordingHandler()
    app_logger = logging.getLogger("app")
    app_logger.addHandler(handler)
    app = create_app()
    configure_debug_logging(enabled=True)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/not-found")
    finally:
        app_logger.removeHandler(handler)
        configure_debug_logging(enabled=False)

    assert response.status_code == httpx.codes.NOT_FOUND
    assert any(
        record.name == "app.requests"
        and "method=GET" in record.getMessage()
        and "status=404" in record.getMessage()
        for record in records
    )
