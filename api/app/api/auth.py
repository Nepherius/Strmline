from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, get_current_user
from app.core.config import get_settings
from app.db.dependencies import get_db_session
from app.db.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])
ph = PasswordHasher()
logger = logging.getLogger(__name__)

# In-memory rate limiter for login attempts.
# NOTE: This is process-local and does not survive restarts or share across
# Gunicorn workers.  Acceptable for MVP single-process Uvicorn; revisit if
# multi-worker deployment is needed.
_login_attempts: dict[str, list[datetime]] = {}
_setup_lock = asyncio.Lock()

MAX_FAILED_ATTEMPTS = 5
MAX_TRACKED_IPS = 1000
SETUP_ADVISORY_LOCK_ID = 8_607_080_010
CSRF_TOKEN_BYTES = 32


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserSetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8)


class UserResponse(BaseModel):
    id: int
    username: str


def _check_rate_limit(ip: str) -> None:
    """Reject the request if too many recent failed attempts from this IP."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=1)

    attempts = [t for t in _login_attempts.get(ip, []) if t > cutoff]
    _login_attempts[ip] = attempts

    if len(attempts) >= MAX_FAILED_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again in a minute.",
        )


def _record_failed_attempt(ip: str) -> None:
    """Record a failed login attempt for rate-limiting purposes."""
    _login_attempts.setdefault(ip, []).append(datetime.now(UTC))
    _evict_stale_ips()


def _evict_stale_ips() -> None:
    """Remove stale entries to prevent unbounded memory growth."""
    if len(_login_attempts) <= MAX_TRACKED_IPS:
        return
    cutoff = datetime.now(UTC) - timedelta(minutes=1)
    stale = [ip for ip, ts in _login_attempts.items() if all(t <= cutoff for t in ts)]
    for ip in stale:
        del _login_attempts[ip]


@router.post("/setup", response_model=UserResponse)
async def setup_first_user(
    request: Request,
    response: Response,
    setup_data: UserSetupRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserResponse:
    client_ip = _client_ip(request)
    _check_rate_limit(client_ip)
    async with _setup_lock:
        await _acquire_setup_lock(session)
        user_count_result = await session.execute(select(User).limit(1))
        if user_count_result.scalar_one_or_none() is not None:
            raise_setup_complete()

        hashed = ph.hash(setup_data.password)
        user = User(username=setup_data.username, hashed_password=hashed)
        session.add(user)
        try:
            await session.commit()
        except IntegrityError as error:
            await session.rollback()
            _record_failed_attempt(client_ip)
            _audit("setup_failed", client_ip, setup_data.username)
            raise setup_complete_error() from error
        await session.refresh(user)

    _issue_session_cookie(request, response, user.id)
    _ = _login_attempts.pop(client_ip, None)
    _audit("setup_succeeded", client_ip, user.username)

    return UserResponse(id=user.id, username=user.username)


@router.post("/login", response_model=UserResponse)
async def login(
    request: Request,
    response: Response,
    login_data: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserResponse:
    client_ip = _client_ip(request)
    _check_rate_limit(client_ip)

    result = await session.execute(select(User).where(User.username == login_data.username))
    user = result.scalar_one_or_none()

    if not user:
        _record_failed_attempt(client_ip)
        _audit("login_failed", client_ip, login_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    try:
        _ = ph.verify(user.hashed_password, login_data.password)
    except VerifyMismatchError as error:
        _record_failed_attempt(client_ip)
        _audit("login_failed", client_ip, login_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        ) from error

    _ = _login_attempts.pop(client_ip, None)

    _issue_session_cookie(request, response, user.id)
    _audit("login_succeeded", client_ip, user.username)
    return UserResponse(id=user.id, username=user.username)


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict[str, str]:
    _audit("logout", _client_ip(request), None)
    secure_cookie = _secure_cookie(request)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=secure_cookie,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
        secure=secure_cookie,
        httponly=False,
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


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _audit(event: str, ip: str, username: str | None) -> None:
    safe_username = username.replace("\r", "").replace("\n", "") if username else "-"
    logger.info("Authentication event=%s ip=%s username=%s", event, ip, safe_username)


def _get_secret_key() -> str:
    """Return the app secret key or raise if not configured."""
    settings = get_settings()
    if settings.app_secret_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="App secret key is not configured. Set STRMLINE_APP_SECRET_KEY.",
        )
    return settings.app_secret_key.get_secret_value()


def _issue_session_cookie(request: Request, response: Response, user_id: int) -> None:
    secret_key = _get_secret_key()
    now = datetime.now(UTC)
    expiration = now + timedelta(days=7)
    csrf_token = secrets.token_urlsafe(CSRF_TOKEN_BYTES)
    secure_cookie = _secure_cookie(request)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expiration.timestamp()),
        "csrf": csrf_token,
    }
    token = jwt.encode(payload, secret_key, algorithm="HS256")  # pyright: ignore[reportUnknownMemberType]

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        expires=expiration,
        path="/",
        httponly=True,
        samesite="lax",
        secure=secure_cookie,
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        expires=expiration,
        path="/",
        httponly=False,
        samesite="lax",
        secure=secure_cookie,
    )


async def _acquire_setup_lock(session: AsyncSession) -> None:
    get_bind = getattr(session, "get_bind", None)
    if not callable(get_bind):
        return
    bind = get_bind()
    dialect_name = getattr(getattr(bind, "dialect", None), "name", None)
    if dialect_name != "postgresql":
        return
    _ = await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": SETUP_ADVISORY_LOCK_ID},
    )


def _secure_cookie(request: Request) -> bool:
    settings = get_settings()
    if settings.secure_cookies is not None:
        return settings.secure_cookies
    return request.url.scheme == "https"


def raise_setup_complete() -> None:
    raise setup_complete_error()


def setup_complete_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Setup is already complete. Admin user already exists.",
    )
