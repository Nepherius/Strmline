from pathlib import Path

import httpx
import pytest

from app.api import library as library_api, setup as setup_api
from app.core.config import get_settings
from app.db.dependencies import get_db_session, get_optional_db_session
from app.library.classification_override import LibraryClassificationOverride
from app.library.removal import LibraryRemovalResult
from app.library.summary import LibraryEntrySummary, LibrarySummary
from app.main import create_app
from tests.conftest import override_auth


@pytest.mark.asyncio
async def test_health_endpoint_returns_service_status() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/health")

    assert response.status_code == httpx.codes.OK
    assert response.json() == {
        "service": "Strmline",
        "status": "ok",
        "version": "0.1.0",
    }


@pytest.mark.asyncio
async def test_cors_preflight_uses_explicit_allowed_methods() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        allowed_response = await client.options(
            "/api/settings",
            headers={
                "origin": "http://127.0.0.1:5173",
                "access-control-request-method": "POST",
            },
        )
        rejected_response = await client.options(
            "/api/settings",
            headers={
                "origin": "http://127.0.0.1:5173",
                "access-control-request-method": "PATCH",
            },
        )

    assert allowed_response.status_code == httpx.codes.OK
    assert rejected_response.status_code == httpx.codes.BAD_REQUEST


@pytest.mark.asyncio
async def test_static_ui_serves_index_for_app_routes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = (tmp_path / "index.html").write_text("<main>Strmline UI</main>", encoding="utf-8")
    monkeypatch.setenv("STRMLINE_STATIC_DIR", str(tmp_path))
    get_settings.cache_clear()

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        root_response = await client.get("/")
        setup_response = await client.get("/setup")
        api_response = await client.get("/api/not-found")

    get_settings.cache_clear()
    assert root_response.status_code == httpx.codes.OK
    assert "Strmline UI" in root_response.text
    assert setup_response.status_code == httpx.codes.OK
    assert "Strmline UI" in setup_response.text
    assert api_response.status_code == httpx.codes.NOT_FOUND


@pytest.mark.asyncio
async def test_setup_status_reports_missing_required_settings() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/setup/status")

    assert response.status_code == httpx.codes.OK
    assert response.json() == {
        "configured": False,
        "missing": ["torbox_api_key", "admin_user"],
    }


@pytest.mark.asyncio
async def test_setup_status_can_use_database_saved_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STRMLINE_BASE_URL", raising=False)
    monkeypatch.delenv("STRMLINE_LIBRARY_ROOT", raising=False)
    monkeypatch.delenv("STRMLINE_TMDB_API_KEY", raising=False)
    monkeypatch.delenv("STRMLINE_TORBOX_API_KEY", raising=False)
    monkeypatch.delenv("STRMLINE_RESOLVER_TOKEN", raising=False)
    monkeypatch.setenv("STRMLINE_DATABASE_URL", "postgresql://example")
    get_settings.cache_clear()

    monkeypatch.setattr(
        setup_api, "AppSettingsRepository", fake_complete_settings_repository(tmp_path)
    )

    app = create_app()
    override_auth(app)
    app.dependency_overrides[get_optional_db_session] = fake_user_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/setup/status")

    get_settings.cache_clear()
    assert response.status_code == httpx.codes.OK
    assert response.json() == {"configured": True, "missing": []}


@pytest.mark.asyncio
async def test_library_summary_reports_configured_library(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library_file = tmp_path / "movies" / "Movie One (2024)" / "Movie One (2024).strm"
    library_file.parent.mkdir(parents=True)
    _ = library_file.write_text("https://example.test/video\n", encoding="utf-8")
    monkeypatch.setenv("STRMLINE_BASE_URL", "http://strmline.test")
    monkeypatch.delenv("STRMLINE_DATABASE_URL", raising=False)
    monkeypatch.setenv("STRMLINE_LIBRARY_ROOT", str(tmp_path))
    monkeypatch.setenv("STRMLINE_TMDB_API_KEY", "tmdb")
    monkeypatch.setenv("STRMLINE_TORBOX_API_KEY", "torbox")
    monkeypatch.setattr(library_api, "_summarize_library", fake_library_summary)
    get_settings.cache_clear()

    app = create_app()
    override_auth(app)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/library/summary")

    get_settings.cache_clear()
    assert response.status_code == httpx.codes.OK
    payload = response.json()
    assert payload["configured"] is True
    assert payload["exists"] is True
    assert payload["total_files"] == 1
    assert payload["category_counts"]["movies"] == 1
    assert payload["entries"][0]["relative_path"] == "movies/Movie One (2024)"


@pytest.mark.asyncio
async def test_library_validation_reports_ready_library(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library_file = tmp_path / "movies" / "Movie One (2024)" / "Movie One (2024).strm"
    library_file.parent.mkdir(parents=True)
    _ = library_file.write_text("https://example.test/video\n", encoding="utf-8")
    monkeypatch.setenv("STRMLINE_LIBRARY_ROOT", str(tmp_path))
    get_settings.cache_clear()

    app = create_app()
    override_auth(app)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/library/validation")

    get_settings.cache_clear()
    assert response.status_code == httpx.codes.OK
    payload = response.json()
    assert payload["configured"] is True
    assert payload["root"] == str(tmp_path)
    assert payload["ok"] is True
    assert payload["total_files"] == 1
    assert payload["errors"] == []


@pytest.mark.asyncio
async def test_library_validation_reports_curation_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library_file = tmp_path / "other" / "Loose.strm"
    library_file.parent.mkdir(parents=True)
    _ = library_file.write_text("https://example.test/video\n", encoding="utf-8")
    monkeypatch.setenv("STRMLINE_LIBRARY_ROOT", str(tmp_path))
    get_settings.cache_clear()

    app = create_app()
    override_auth(app)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/library/validation")

    get_settings.cache_clear()
    assert response.status_code == httpx.codes.OK
    payload = response.json()
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "strm_outside_category"
    assert payload["errors"][0]["relative_path"] == "other/Loose.strm"


@pytest.mark.asyncio
async def test_library_root_defaults_to_internal_docker_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STRMLINE_LIBRARY_ROOT", raising=False)
    monkeypatch.delenv("STRMLINE_DATABASE_URL", raising=False)
    get_settings.cache_clear()

    try:
        library_root = await library_api.get_library_root()
    finally:
        get_settings.cache_clear()

    assert library_root == Path("/library")


@pytest.mark.asyncio
async def test_library_remove_entry_deletes_torbox_item_and_generated_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRMLINE_LIBRARY_ROOT", str(tmp_path))
    monkeypatch.setenv("STRMLINE_TORBOX_API_KEY", "torbox")
    get_settings.cache_clear()
    removed_items: list[tuple[str, str]] = []

    class FakeTorBoxClient:
        def __init__(self, **kwargs: object) -> None:
            _ = kwargs

        async def __aenter__(self) -> "FakeTorBoxClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            _ = args

        async def delete_download(self, kind: str, item_id: str) -> None:
            removed_items.append((kind, item_id))

    monkeypatch.setattr(library_api, "TorBoxClient", FakeTorBoxClient)
    monkeypatch.setattr(library_api, "LibraryExclusionRepository", fake_exclusion_repository)
    monkeypatch.setattr(library_api, "_remove_library_prefix", fake_remove_library_prefix)

    app = create_app()
    override_auth(app)
    app.dependency_overrides[get_db_session] = fake_db_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.request(
            "DELETE",
            "/api/library/entries",
            json={
                "category": "shows",
                "title": "Show One",
                "relative_path": "shows/Show One",
            },
        )

    get_settings.cache_clear()
    assert response.status_code == httpx.codes.OK
    assert response.json() == {
        "ok": True,
        "message": "Library entry removed.",
        "removed_files": 2,
        "removed_torbox_items": 1,
    }
    assert removed_items == [("torrents", "123")]


@pytest.mark.asyncio
async def test_library_remove_entry_can_skip_torbox_removal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRMLINE_LIBRARY_ROOT", str(tmp_path))
    monkeypatch.setenv("STRMLINE_TORBOX_API_KEY", "torbox")
    get_settings.cache_clear()
    removed_items: list[tuple[str, str]] = []

    class FakeTorBoxClient:
        def __init__(self, **kwargs: object) -> None:
            _ = kwargs

        async def __aenter__(self) -> "FakeTorBoxClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            _ = args

        async def delete_download(self, kind: str, item_id: str) -> None:
            removed_items.append((kind, item_id))

    monkeypatch.setattr(library_api, "TorBoxClient", FakeTorBoxClient)
    monkeypatch.setattr(library_api, "LibraryExclusionRepository", fake_exclusion_repository)
    monkeypatch.setattr(library_api, "_remove_library_prefix", fake_remove_library_prefix)

    app = create_app()
    override_auth(app)
    app.dependency_overrides[get_db_session] = fake_db_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.request(
            "DELETE",
            "/api/library/entries",
            json={
                "category": "shows",
                "title": "Show One",
                "relative_path": "shows/Show One/Season 01/Show One - S01E01.strm",
                "remove_torbox": False,
            },
        )

    get_settings.cache_clear()
    assert response.status_code == httpx.codes.OK
    assert response.json()["removed_torbox_items"] == 0
    assert removed_items == []


@pytest.mark.asyncio
async def test_library_classification_override_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[LibraryClassificationOverride] = []

    class FakeClassificationOverrideRepository:
        def __init__(self, session: object) -> None:
            _ = session

        async def list_all(self) -> tuple[LibraryClassificationOverride, ...]:
            return tuple(saved)

        async def upsert(self, **kwargs: object) -> LibraryClassificationOverride:
            override = LibraryClassificationOverride(
                source_category="shows",
                source_prefix=str(kwargs["source_prefix"]),
                title=str(kwargs["title"]),
                target_category="anime",
            )
            saved[:] = [override]
            return override

        async def delete(self, source_prefix: str) -> bool:
            if saved and saved[0].source_prefix == source_prefix:
                saved.clear()
                return True
            return False

    monkeypatch.setattr(
        library_api,
        "ClassificationOverrideRepository",
        FakeClassificationOverrideRepository,
    )

    app = create_app()
    override_auth(app)
    app.dependency_overrides[get_db_session] = fake_db_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        save_response = await client.post(
            "/api/library/classification-overrides",
            json={
                "source_category": "shows",
                "source_prefix": "shows/Frieren",
                "title": "Frieren",
                "target_category": "anime",
            },
        )
        list_response = await client.get("/api/library/classification-overrides")
        delete_response = await client.request(
            "DELETE",
            "/api/library/classification-overrides",
            json={
                "source_category": "shows",
                "source_prefix": "shows/Frieren",
            },
        )

    assert save_response.status_code == httpx.codes.OK
    assert save_response.json() == {
        "source_category": "shows",
        "source_prefix": "shows/Frieren",
        "title": "Frieren",
        "target_category": "anime",
        "target_prefix": "anime/Frieren",
    }
    assert list_response.json() == [save_response.json()]
    assert delete_response.status_code == httpx.codes.NO_CONTENT


async def fake_user_session() -> object:
    yield FakeUserSession()


class FakeResult:
    def scalar_one_or_none(self) -> object:
        return object()


class FakeUserSession:
    async def execute(self, statement: object) -> FakeResult:
        _ = statement
        return FakeResult()


class FakeDbSession:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


async def fake_db_session() -> object:
    yield FakeDbSession()


class FakeExclusionRepository:
    def __init__(self, session: object) -> None:
        _ = session
        self.added: list[tuple[str, str, str]] = []

    async def backing_items(self, relative_prefix: str) -> tuple[object, ...]:
        _ = relative_prefix
        return (type("BackingItem", (), {"kind": "torrents", "item_id": "123"})(),)

    async def add(self, *, category: str, title: str, relative_prefix: str) -> None:
        self.added.append((category, title, relative_prefix))


def fake_exclusion_repository(session: object) -> FakeExclusionRepository:
    return FakeExclusionRepository(session)


async def fake_remove_library_prefix(
    library_root: Path,
    relative_prefix: str,
) -> LibraryRemovalResult:
    _ = (library_root, relative_prefix)
    return LibraryRemovalResult(removed_files=2)


async def fake_library_summary(library_root: Path) -> LibrarySummary:
    return LibrarySummary(
        root=library_root,
        exists=True,
        total_files=1,
        category_counts={"movies": 1, "shows": 0, "anime": 0},
        files=(),
        entries=(
            LibraryEntrySummary(
                key="movies/Movie One (2024)",
                category="movies",
                title="Movie One (2024)",
                relative_path="movies/Movie One (2024)",
                file_count=1,
            ),
        ),
        duplicate_groups=(),
    )


def fake_complete_settings_repository(library_root: Path) -> object:
    class FakeSettingsRepository:
        def __init__(self, session: object, settings: object) -> None:
            _ = session
            _ = settings

        async def snapshot_with_env(self) -> object:
            return type(
                "Snapshot",
                (),
                {
                    "base_url": "http://127.0.0.1:8001",
                    "library_root": str(library_root),
                    "torbox_configured": True,
                    "tmdb_configured": True,
                    "resolver_configured": True,
                    "playback_mode": "resolver",
                },
            )()

    return FakeSettingsRepository
