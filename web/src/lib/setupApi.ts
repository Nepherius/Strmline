import { fetchJson } from "$lib/api";
import type { SetupStatus } from "$lib/settings";

export interface ConnectionTestResult {
  ok: boolean;
  message: string;
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
