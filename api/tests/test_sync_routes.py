from datetime import UTC, datetime

import httpx
import pytest

from app.api import sync as sync_api
from app.db.dependencies import get_db_session
from app.db.repositories.sync_state import SyncErrorRecord, SyncRunRecord, SyncStatusSnapshot
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


@pytest.mark.asyncio
async def test_sync_status_route_reports_last_run_and_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started_at = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)

    class FakeSyncStateRepository:
        def __init__(self, session: object) -> None:
            _ = session

        async def status(self) -> SyncStatusSnapshot:
            return SyncStatusSnapshot(
                last_run=SyncRunRecord(
                    id=8,
                    status="failed",
                    source="manual",
                    started_at=started_at,
                    finished_at=started_at,
                    scanned_count=3,
                    written_count=2,
                    skipped_count=1,
                ),
                last_auto_run=SyncRunRecord(
                    id=7,
                    status="success",
                    source="auto",
                    started_at=started_at,
                    finished_at=started_at,
                    scanned_count=4,
                    written_count=4,
                    skipped_count=0,
                ),
                recent_errors=(
                    SyncErrorRecord(
                        id=9,
                        sync_run_id=8,
                        phase="torbox_sync",
                        item_ref=None,
                        message="TorBox request failed with status 503.",
                        created_at=started_at,
                    ),
                ),
            )

    monkeypatch.setattr(sync_api, "SyncStateRepository", FakeSyncStateRepository)

    response = await _get_sync_status()

    assert response.status_code == httpx.codes.OK
    assert response.json() == {
        "last_run": {
            "id": 8,
            "status": "failed",
            "source": "manual",
            "started_at": "2026-07-04T12:00:00+00:00",
            "finished_at": "2026-07-04T12:00:00+00:00",
            "scanned_count": 3,
            "written_count": 2,
            "skipped_count": 1,
        },
        "last_auto_run": {
            "id": 7,
            "status": "success",
            "source": "auto",
            "started_at": "2026-07-04T12:00:00+00:00",
            "finished_at": "2026-07-04T12:00:00+00:00",
            "scanned_count": 4,
            "written_count": 4,
            "skipped_count": 0,
        },
        "recent_errors": [
            {
                "id": 9,
                "sync_run_id": 8,
                "phase": "torbox_sync",
                "item_ref": None,
                "message": "TorBox request failed with status 503.",
                "created_at": "2026-07-04T12:00:00+00:00",
            }
        ],
    }


async def _post_sync_run() -> httpx.Response:
    app = create_app()
    app.dependency_overrides[get_db_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post("/api/sync/run")


async def _get_sync_status() -> httpx.Response:
    app = create_app()
    app.dependency_overrides[get_db_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get("/api/sync/status")


async def _session_override() -> object:
    yield object()
