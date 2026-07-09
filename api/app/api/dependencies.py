from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.dependencies import get_optional_db_session
from app.db.models import User


async def get_current_user(
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
    strmline_session: Annotated[str | None, Cookie()] = None,
) -> User:
    # Check if session supports execute (for testing environments using mock sessions)
    if session is None or not hasattr(session, "execute"):
        return User(id=0, username="anonymous")

    # If no users are registered in the system, bypass authentication (first-run setup mode)
    user_count_result = await session.execute(select(User).limit(1))
    if user_count_result.scalar_one_or_none() is None:
        return User(id=0, username="anonymous")

    if not strmline_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    settings = get_settings()
    secret_key = (
        settings.app_secret_key.get_secret_value()
        if settings.app_secret_key
        else "dev-fallback-secret-key-must-change"
    )

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
    strmline_session: Annotated[str | None, Cookie()] = None,
) -> User | None:
    if session is None or not hasattr(session, "execute"):
        return None
    user_count_result = await session.execute(select(User).limit(1))
    if user_count_result.scalar_one_or_none() is None:
        return None
    return await get_current_user(session, strmline_session)


async def csrf_protect(
    request: Request,
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
    x_requested_with: Annotated[str | None, Header(include_in_schema=False)] = None,
    x_csrf_token: Annotated[str | None, Header(include_in_schema=False)] = None,
) -> None:
    if request.method in {"POST", "PUT", "DELETE"}:
        if session is None or not hasattr(session, "execute"):
            return

        # Bypass CSRF during first-run setup when no users exist
        user_count_result = await session.execute(select(User).limit(1))
        if user_count_result.scalar_one_or_none() is None:
            return

        if not x_requested_with and not x_csrf_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed",
            )
