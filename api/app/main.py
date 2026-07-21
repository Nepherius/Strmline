import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint

from app.api.aiostreams import router as aiostreams_router
from app.api.auth import router as auth_router
from app.api.dependencies import (
    csrf_protect,
    get_current_user,
    get_current_user_or_anonymous_if_no_users,
)
from app.api.health import router as health_router
from app.api.library import router as library_router
from app.api.logs import router as logs_router
from app.api.operations import router as operations_router
from app.api.resolver import clear_resolved_target_cache, router as resolver_router
from app.api.search import router as search_router
from app.api.settings import configure_operational_runtime, router as settings_router
from app.api.setup import router as setup_router
from app.api.sync import router as sync_router
from app.api.watchlist import router as watchlist_router
from app.core.config import get_settings
from app.core.error_logging import ErrorLogWriter
from app.core.logging import configure_debug_logging
from app.db.dependencies import get_session_factory
from app.db.repositories.settings import AppSettingsRepository
from app.providers.torbox.runtime import clear_torbox_runtime, get_torbox_request_coordinator
from app.static_ui import mount_static_ui
from app.sync.scheduler import shutdown_auto_sync_scheduler, start_auto_sync_scheduler

_SWAGGER_CDN = "https://cdn.jsdelivr.net"
_SWAGGER_FAVICON = "https://fastapi.tiangolo.com"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    error_log_writer = ErrorLogWriter(settings.log_dir)
    await error_log_writer.start()
    app.state.error_log_writer = error_log_writer
    try:
        if settings.database_url is not None:
            async with get_session_factory()() as session:
                snapshot = await AppSettingsRepository(session, settings).snapshot_with_env()
            configure_debug_logging(enabled=snapshot.debug_logging)
            configure_operational_runtime(snapshot)
        torbox_coordinator = get_torbox_request_coordinator()
        logging.getLogger(__name__).info(
            "TorBox request budget configured requests_per_minute=%d.",
            torbox_coordinator.requests_per_minute,
        )
        await start_auto_sync_scheduler(app)
        yield
    finally:
        clear_resolved_target_cache()
        clear_torbox_runtime()
        await shutdown_auto_sync_scheduler(app)
        await error_log_writer.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_debug_logging(enabled=False)
    docs_enabled = settings.api_docs_enabled
    app = FastAPI(
        title=settings.service_name,
        version=settings.version,
        lifespan=lifespan,
        debug=False,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=list(settings.cors_methods),
        allow_headers=list(settings.cors_headers),
    )

    script_hashes: tuple[str, ...] = ()

    @app.middleware("http")
    async def security_headers(  # pyright: ignore[reportUnusedFunction]
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        started_at = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logging.getLogger(__name__).exception("Unhandled request failure.")
            raise
        if request.url.path != "/api/health":
            logging.getLogger("app.requests").debug(
                "Request completed method=%s route=%s status=%d duration_ms=%.1f.",
                request.method,
                _route_path(request),
                response.status_code,
                (perf_counter() - started_at) * 1000,
            )
        response.headers["Content-Security-Policy"] = _content_security_policy(
            request.url.path, script_hashes
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    app.include_router(auth_router)
    app.include_router(health_router)
    app.include_router(resolver_router)
    app.include_router(
        setup_router,
        dependencies=[
            Depends(get_current_user_or_anonymous_if_no_users),
            Depends(csrf_protect),
        ],
    )

    app.include_router(
        settings_router,
        dependencies=[
            Depends(get_current_user_or_anonymous_if_no_users),
            Depends(csrf_protect),
        ],
    )
    app.include_router(
        aiostreams_router,
        dependencies=[Depends(get_current_user), Depends(csrf_protect)],
    )
    app.include_router(
        library_router,
        dependencies=[Depends(get_current_user), Depends(csrf_protect)],
    )
    app.include_router(
        search_router,
        dependencies=[Depends(get_current_user), Depends(csrf_protect)],
    )
    app.include_router(
        watchlist_router,
        dependencies=[Depends(get_current_user), Depends(csrf_protect)],
    )
    app.include_router(
        sync_router,
        dependencies=[Depends(get_current_user), Depends(csrf_protect)],
    )
    app.include_router(
        logs_router,
        dependencies=[Depends(get_current_user), Depends(csrf_protect)],
    )
    app.include_router(
        operations_router,
        dependencies=[Depends(get_current_user), Depends(csrf_protect)],
    )
    script_hashes = mount_static_ui(app, settings.static_dir)
    return app


def _route_path(request: Request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    return route_path if isinstance(route_path, str) else request.url.path


app = create_app()


def _content_security_policy(path: str, script_hashes: tuple[str, ...]) -> str:
    if path == "/docs":
        return (
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; "
            "form-action 'self'; img-src 'self' https://image.tmdb.org "
            f"{_SWAGGER_FAVICON} data:; style-src 'self' {_SWAGGER_CDN} 'unsafe-inline'; "
            f"script-src 'self' {_SWAGGER_CDN} 'unsafe-inline'; connect-src 'self'"
        )

    script_sources = " ".join(f"'{script_hash}'" for script_hash in script_hashes)
    return (
        "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; "
        "form-action 'self'; img-src 'self' https://image.tmdb.org data:; "
        f"style-src 'self' 'unsafe-inline'; script-src 'self' {script_sources}; "
        "connect-src 'self'"
    )
