from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.dependencies import get_db_session
from app.db.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])
ph = PasswordHasher()

_login_attempts: dict[str, list[datetime]] = {}


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserSetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8)


class UserResponse(BaseModel):
    id: int
    username: str


MAX_FAILED_ATTEMPTS = 5


def _check_rate_limit(ip: str) -> None:
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=1)

    attempts = [t for t in _login_attempts.get(ip, []) if t > cutoff]
    _login_attempts[ip] = attempts

    if len(attempts) >= MAX_FAILED_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again in a minute.",
        )

    attempts.append(now)


@router.post("/setup", response_model=UserResponse)
async def setup_first_user(
    request: Request,
    response: Response,
    setup_data: UserSetupRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserResponse:
    user_count_result = await session.execute(select(User).limit(1))
    if user_count_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Setup is already complete. Admin user already exists.",
        )

    hashed = ph.hash(setup_data.password)
    user = User(username=setup_data.username, hashed_password=hashed)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    _issue_session_cookie(request, response, user.id)

    return UserResponse(id=user.id, username=user.username)


@router.post("/login", response_model=UserResponse)
async def login(
    request: Request,
    response: Response,
    login_data: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserResponse:
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    result = await session.execute(select(User).where(User.username == login_data.username))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    try:
        _ = ph.verify(user.hashed_password, login_data.password)
    except VerifyMismatchError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        ) from error

    _ = _login_attempts.pop(client_ip, None)

    _issue_session_cookie(request, response, user.id)
    return UserResponse(id=user.id, username=user.username)


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(
        key="strmline_session",
        path="/",
        httponly=True,
        samesite="lax",
    )
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    return UserResponse(id=current_user.id, username=current_user.username)


def clear_login_attempts() -> None:
    """Clear all login attempts (used in tests)."""
    _login_attempts.clear()


def _issue_session_cookie(request: Request, response: Response, user_id: int) -> None:
    settings = get_settings()
    secret_key = (
        settings.app_secret_key.get_secret_value()
        if settings.app_secret_key
        else "dev-fallback-secret-key-must-change"
    )

    expiration = datetime.now(UTC) + timedelta(days=7)
    payload = {
        "sub": str(user_id),
        "exp": int(expiration.timestamp()),
    }
    token = jwt.encode(payload, secret_key, algorithm="HS256")  # pyright: ignore[reportUnknownMemberType]

    response.set_cookie(
        key="strmline_session",
        value=token,
        expires=expiration,
        path="/",
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
