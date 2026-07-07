import { fetchJson } from "$lib/api/client";
import type { SetupStatus } from "$lib/domain/settings";

export interface ConnectionTestResult {
  ok: boolean;
  message: string;
}

export interface AioStreamsStreamPreview {
  name: string | null;
  title: string | null;
  description: string | null;
  has_url: boolean;
  has_info_hash: boolean;
  file_idx: number | null;
  behavior_hints: {
    filename?: string;
    videoSize?: number;
    bingeGroup?: string;
  };
}

export interface AioStreamsTestResult extends ConnectionTestResult {
  addon_name: string | null;
  addon_version: string | null;
  resources: string[];
  types: string[];
  stream_count: number | null;
  streams: AioStreamsStreamPreview[];
}

export function loadSetupStatus(): Promise<SetupStatus> {
  return fetchJson<SetupStatus>("/api/setup/status");
}

export function buildTorboxConnectionTestPayload(apiKey: string): Record<string, string> {
  const trimmedApiKey = apiKey.trim();
  return trimmedApiKey ? { torbox_api_key: trimmedApiKey } : {};
}

export function buildTmdbConnectionTestPayload(apiKey: string): Record<string, string> {
  const trimmedApiKey = apiKey.trim();
  return trimmedApiKey ? { tmdb_api_key: trimmedApiKey } : {};
}

export function buildAioStreamsTestPayload(baseUrl: string): Record<string, string> {
  const payload: Record<string, string> = {};
  const trimmedBaseUrl = baseUrl.trim();
  if (trimmedBaseUrl) payload["base_url"] = trimmedBaseUrl;
  return payload;
}

export function testTorboxConnection(apiKey: string): Promise<ConnectionTestResult> {
  return fetchJson<ConnectionTestResult>("/api/setup/test/torbox", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(buildTorboxConnectionTestPayload(apiKey)),
  });
}

export function testTmdbConnection(apiKey: string): Promise<ConnectionTestResult> {
  return fetchJson<ConnectionTestResult>("/api/setup/test/tmdb", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(buildTmdbConnectionTestPayload(apiKey)),
  });
}

export function testAioStreamsConnection(baseUrl: string): Promise<AioStreamsTestResult> {
  return fetchJson<AioStreamsTestResult>("/api/providers/aiostreams/test", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(buildAioStreamsTestPayload(baseUrl)),
  });
}
