import { fetchJson } from "$lib/api/client";

export interface TorBoxOperationsMetrics {
  request_budget_per_minute: number;
  requests_total: number;
  requests_succeeded: number;
  requests_failed: number;
  responses_429: number;
  calls_last_minute: number;
  queue_depth: number;
}

export interface ResolverOperationsMetrics {
  cache_hits: number;
  cache_misses: number;
  negative_cache_hits: number;
  circuit_open_rejections: number;
  recovery_attempts: number;
  recovery_succeeded: number;
  recovery_failed: number;
}

export interface OperationsMetrics {
  torbox: TorBoxOperationsMetrics;
  resolver: ResolverOperationsMetrics;
}

export function loadOperationsMetrics(): Promise<OperationsMetrics> {
  return fetchJson<OperationsMetrics>("/api/operations/metrics");
}
