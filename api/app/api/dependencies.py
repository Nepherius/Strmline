from __future__ import annotations

from hmac import compare_digest
from typing import Annotated, NoReturn

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.dependencies import get_optional_db_session
from app.db.models import User

SESSION_COOKIE_NAME = "strmline_session"
CSRF_COOKIE_NAME = "strmline_csrf"
MUTATING_METHODS = {"POST", "PUT", "DELETE"}


async def get_current_user(
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
    strmline_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> User:
    if session is None or not hasattr(session, "execute"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not available.",
        )

    if not strmline_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    settings = get_settings()
    if settings.app_secret_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="App secret key is not configured.",
        )
    secret_key = settings.app_secret_key.get_secret_value()

    try:
        payload = jwt.decode(strmline_session, secret_key, algorithms=["HS256"])  # pyright: ignore[reportUnknownMemberType]
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token session",
            )
        user_id = int(user_id_str)
    except (jwt.PyJWTError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or is invalid",
        ) from error

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


async def get_current_user_or_anonymous_if_no_users(
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
    strmline_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> User | None:
    if session is None or not hasattr(session, "execute"):
        return None
    if not await registered_user_exists(session):
        return None
    return await get_current_user(session, strmline_session)


async def csrf_protect(
    request: Request,
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
    strmline_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    strmline_csrf: Annotated[str | None, Cookie(alias=CSRF_COOKIE_NAME)] = None,
    x_csrf_token: Annotated[str | None, Header(include_in_schema=False)] = None,
) -> None:
    if request.method not in MUTATING_METHODS:
        return
    if session is None or not hasattr(session, "execute"):
        return
    if not await registered_user_exists(session):
        return
    validate_csrf_tokens(strmline_session, strmline_csrf, x_csrf_token)


def validate_csrf_tokens(
    strmline_session: str | None,
    strmline_csrf: str | None,
    x_csrf_token: str | None,
) -> None:
    if strmline_session is None or strmline_csrf is None or x_csrf_token is None:
        raise_csrf_error()
    session_token: str = strmline_session
    csrf_cookie: str = strmline_csrf
    csrf_header: str = x_csrf_token

    settings = get_settings()
    if settings.app_secret_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="App secret key is not configured.",
        )

    try:
        payload = jwt.decode(  # pyright: ignore[reportUnknownMemberType]
            session_token,
            settings.app_secret_key.get_secret_value(),
            algorithms=["HS256"],
        )
    except jwt.PyJWTError as error:
        raise csrf_error() from error

    session_csrf = payload.get("csrf")
    if not isinstance(session_csrf, str):
        raise_csrf_error()
    if not compare_digest(session_csrf, csrf_cookie):
        raise_csrf_error()
    if not compare_digest(session_csrf, csrf_header):
        raise_csrf_error()


async def registered_user_exists(session: AsyncSession) -> bool:
    user_count_result = await session.execute(select(User).limit(1))
    return user_count_result.scalar_one_or_none() is not None


def raise_csrf_error() -> NoReturn:
    raise csrf_error()


def csrf_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="CSRF validation failed",
    )
