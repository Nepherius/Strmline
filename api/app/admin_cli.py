"""Administrative recovery commands intended for use inside the app container."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from collections.abc import Sequence

from argon2 import PasswordHasher
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import User
from app.db.session import build_session_factory

MINIMUM_PASSWORD_LENGTH = 8


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="strmline-admin")
    subparsers = parser.add_subparsers(dest="command")
    _ = subparsers.add_parser(
        "reset-password",
        help="Reset the configured administrator password.",
    )
    args = parser.parse_args(argv)
    if args.command != "reset-password":
        parser.print_help()
        return 1

    password = _prompt_password()
    if password is None:
        return 2
    return asyncio.run(_reset_password(password))


async def _reset_password(password: str) -> int:
    settings = get_settings()
    if settings.database_url is None:
        _write_error("A database connection is required to reset the administrator password.")
        return 2
    try:
        session_factory = build_session_factory(settings.database_url)
        async with session_factory() as session:
            username = await reset_first_user_password(session, password)
    except SQLAlchemyError:
        _write_error("Could not update the administrator password.")
        return 1
    if username is None:
        _write_error("No administrator account has been configured.")
        return 1
    _write_output(f"Password reset for username: {username}\n")
    return 0


async def reset_first_user_password(session: AsyncSession, password: str) -> str | None:
    result = await session.execute(select(User).order_by(User.id).limit(1))
    user = result.scalar_one_or_none()
    if user is None:
        return None
    user.hashed_password = PasswordHasher().hash(password)
    await session.commit()
    return user.username


def _prompt_password() -> str | None:
    password = getpass.getpass("New administrator password: ")
    confirmation = getpass.getpass("Confirm new administrator password: ")
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        _write_error(f"Password must be at least {MINIMUM_PASSWORD_LENGTH} characters.")
        return None
    if password != confirmation:
        _write_error("Password confirmation does not match.")
        return None
    return password


def _write_output(message: str) -> None:
    _ = sys.stdout.write(message)


def _write_error(message: str) -> None:
    _ = sys.stderr.write(f"{message}\n")


if __name__ == "__main__":
    raise SystemExit(main())
