from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/api/setup", tags=["setup"])


class SetupStatusResponse(BaseModel):
    configured: bool
    missing: list[str]


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status() -> SetupStatusResponse:
    settings = get_settings()
    missing = settings.missing_setup_fields()
    return SetupStatusResponse(
        configured=not missing,
        missing=missing,
    )
