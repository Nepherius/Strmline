from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/api/health", tags=["health"])


class HealthResponse(BaseModel):
    service: str
    status: Literal["ok"]
    version: str


@router.get("", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(service=settings.service_name, status="ok", version=settings.version)
