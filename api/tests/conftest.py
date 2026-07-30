"""Shared test fixtures and helpers for Strmline API tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.api.dependencies import get_current_user, get_current_user_or_anonymous_if_no_users
from app.db.models import User
from app.providers.aiostreams.result_cache import clear_aiostreams_result_cache
from app.providers.torbox.manifest_cache import clear_torbox_manifest_cache


@pytest.fixture(autouse=True)
def reset_process_local_caches() -> None:
    clear_aiostreams_result_cache()
    clear_torbox_manifest_cache()


async def _fake_authenticated_user() -> User:
    """Return a fake authenticated user for tests that bypass real auth."""
    user = User(username="testadmin", hashed_password="fake-hash")  # noqa: S106
    user.id = 1
    return user


def override_auth(app: object) -> None:
    """Override get_current_user so protected routes accept unauthenticated test requests."""
    if not isinstance(app, FastAPI):
        return
    app.dependency_overrides[get_current_user] = _fake_authenticated_user
    app.dependency_overrides[get_current_user_or_anonymous_if_no_users] = _fake_authenticated_user
