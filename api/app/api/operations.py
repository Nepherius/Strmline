from fastapi import APIRouter
from pydantic import BaseModel

from app.operations.metrics import get_operational_metrics
from app.providers.torbox.runtime import get_torbox_request_coordinator

router = APIRouter(prefix="/api/operations", tags=["operations"])


class TorBoxOperationsResponse(BaseModel):
    request_budget_per_minute: int
    requests_total: int
    requests_succeeded: int
    requests_failed: int
    responses_429: int
    calls_last_minute: int
    queue_depth: int


class ResolverOperationsResponse(BaseModel):
    cache_hits: int
    cache_misses: int
    negative_cache_hits: int
    circuit_open_rejections: int
    recovery_attempts: int
    recovery_succeeded: int
    recovery_failed: int


class OperationsMetricsResponse(BaseModel):
    torbox: TorBoxOperationsResponse
    resolver: ResolverOperationsResponse


@router.get("/metrics", response_model=OperationsMetricsResponse)
async def operations_metrics() -> OperationsMetricsResponse:
    _ = get_torbox_request_coordinator()
    snapshot = get_operational_metrics().snapshot()
    return OperationsMetricsResponse(
        torbox=TorBoxOperationsResponse(
            request_budget_per_minute=snapshot.torbox_request_budget_per_minute,
            requests_total=snapshot.torbox_requests_total,
            requests_succeeded=snapshot.torbox_requests_succeeded,
            requests_failed=snapshot.torbox_requests_failed,
            responses_429=snapshot.torbox_responses_429,
            calls_last_minute=snapshot.torbox_calls_last_minute,
            queue_depth=snapshot.torbox_queue_depth,
        ),
        resolver=ResolverOperationsResponse(
            cache_hits=snapshot.resolver_cache_hits,
            cache_misses=snapshot.resolver_cache_misses,
            negative_cache_hits=snapshot.resolver_negative_cache_hits,
            circuit_open_rejections=snapshot.resolver_circuit_open_rejections,
            recovery_attempts=snapshot.resolver_recovery_attempts,
            recovery_succeeded=snapshot.resolver_recovery_succeeded,
            recovery_failed=snapshot.resolver_recovery_failed,
        ),
    )
