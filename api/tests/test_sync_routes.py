import httpx
import pytest

from app.api import sync as sync_api
from app.db.dependencies import get_db_session
from app.main import create_app
from app.sync.service import SyncAlreadyRunningError, SyncConfigurationError, SyncRunSummary


@pytest.mark.asyncio
async def test_sync_run_route_reports_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_torbox_account_sync(*args: object, **kwargs: object) -> SyncRunSummary:
        _ = args
        _ = kwargs
        return SyncRunSummary(
            sync_run_id=7,
            playback_mode="resolver",
            library_root="/library",
            scanned_files=5,
            written_files=5,
            skipped_files=2,
        )

    monkeypatch.setattr(sync_api, "run_torbox_account_sync", fake_run_torbox_account_sync)

    response = await _post_sync_run()

    assert response.status_code == httpx.codes.OK
    assert response.json() == {
        "sync_run_id": 7,
        "playback_mode": "resolver",
        "library_root": "/library",
        "scanned_files": 5,
        "written_files": 5,
        "skipped_files": 2,
    }


@pytest.mark.asyncio
async def test_sync_run_route_reports_running_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_torbox_account_sync(*args: object, **kwargs: object) -> SyncRunSummary:
        _ = args
        _ = kwargs
        raise SyncAlreadyRunningError("A sync run is already in progress.")

    monkeypatch.setattr(sync_api, "run_torbox_account_sync", fake_run_torbox_account_sync)

    response = await _post_sync_run()

    assert response.status_code == httpx.codes.CONFLICT


@pytest.mark.asyncio
async def test_sync_run_route_reports_configuration_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_torbox_account_sync(*args: object, **kwargs: object) -> SyncRunSummary:
        _ = args
        _ = kwargs
        raise SyncConfigurationError("TorBox API key is not configured.")

    monkeypatch.setattr(sync_api, "run_torbox_account_sync", fake_run_torbox_account_sync)

    response = await _post_sync_run()

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert response.json() == {"detail": "TorBox API key is not configured."}


async def _post_sync_run() -> httpx.Response:
    app = create_app()
    app.dependency_overrides[get_db_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post("/api/sync/run")


async def _session_override() -> object:
    yield object()
