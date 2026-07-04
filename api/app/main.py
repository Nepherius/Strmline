from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.library import router as library_router
from app.api.resolver import router as resolver_router
from app.api.settings import router as settings_router
from app.api.setup import router as setup_router
from app.api.sync import router as sync_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.service_name,
        version=settings.version,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=list(settings.cors_methods),
        allow_headers=list(settings.cors_headers),
    )
    app.include_router(health_router)
    app.include_router(library_router)
    app.include_router(resolver_router)
    app.include_router(settings_router)
    app.include_router(setup_router)
    app.include_router(sync_router)
    return app


app = create_app()
