from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.setup import router as setup_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.service_name,
        version=settings.version,
    )
    app.include_router(health_router)
    app.include_router(setup_router)
    return app


app = create_app()
