"""Runtime logging configuration without exposing sensitive values."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
_HANDLER_MARKER = "strmline_app_handler"


def configure_debug_logging(*, enabled: bool) -> None:
    """Apply the persisted debug setting without enabling HTTP client request logs."""
    level = logging.DEBUG if enabled else logging.INFO
    app_logger = logging.getLogger("app")
    app_logger.setLevel(level)
    app_logger.propagate = False
    handler = _app_handler(app_logger)
    handler.setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logger.info("Debug logging %s.", "enabled" if enabled else "disabled")


def _app_handler(app_logger: logging.Logger) -> logging.Handler:
    for handler in app_logger.handlers:
        if getattr(handler, _HANDLER_MARKER, False):
            return handler
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    setattr(handler, _HANDLER_MARKER, True)
    app_logger.addHandler(handler)
    return handler
