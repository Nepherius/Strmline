import logging

from app.core.logging import configure_debug_logging


def test_debug_logging_changes_app_log_level() -> None:
    configure_debug_logging(enabled=True)
    assert logging.getLogger("app").getEffectiveLevel() == logging.DEBUG
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING

    configure_debug_logging(enabled=False)
    assert logging.getLogger("app").getEffectiveLevel() == logging.INFO
