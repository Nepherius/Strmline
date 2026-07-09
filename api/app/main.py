from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.aiostreams import router as aiostreams_router
from app.api.auth import router as auth_router
from app.api.dependencies import (
    csrf_protect,
    get_current_user,
    get_current_user_or_anonymous_if_no_users,
)
from app.api.health import router as health_router
from app.api.library import router as library_router
from app.api.resolver import router as resolver_router
from app.api.search import router as search_router
from app.api.settings import router as settings_router
from app.api.setup import router as setup_router
from app.api.sync import router as sync_router
from app.core.config import get_settings
from app.static_ui import mount_static_ui
from app.sync.scheduler import shutdown_auto_sync_scheduler, start_auto_sync_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    await start_auto_sync_scheduler(app)
    try:
        yield
    finally:
        await shutdown_auto_sync_scheduler(app)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.service_name,
        version=settings.version,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=list(settings.cors_methods),
        allow_headers=list(settings.cors_headers),
    )
    app.include_router(auth_router)
    app.include_router(health_router)
    app.include_router(resolver_router)
    app.include_router(setup_router)

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
        sync_router,
        dependencies=[Depends(get_current_user), Depends(csrf_protect)],
    )
    mount_static_ui(app, settings.static_dir)

    return app


app = create_app()
