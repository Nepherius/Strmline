import { fetchJson } from "$lib/api";
import type { SetupStatus } from "$lib/settings";

export interface ConnectionTestResult {
  ok: boolean;
  message: string;
}

export function loadSetupStatus(apiBase: string): Promise<SetupStatus> {
  return fetchJson<SetupStatus>(apiBase, "/api/setup/status");
}

export function buildTorboxConnectionTestPayload(apiKey: string): Record<string, string> {
  const trimmedApiKey = apiKey.trim();
  return trimmedApiKey ? { torbox_api_key: trimmedApiKey } : {};
}

export function buildTmdbConnectionTestPayload(apiKey: string): Record<string, string> {
  const trimmedApiKey = apiKey.trim();
  return trimmedApiKey ? { tmdb_api_key: trimmedApiKey } : {};
}

export function testTorboxConnection(
  apiBase: string,
  apiKey: string,
): Promise<ConnectionTestResult> {
  return fetchJson<ConnectionTestResult>(apiBase, "/api/setup/test/torbox", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(buildTorboxConnectionTestPayload(apiKey)),
  });
}

export function testTmdbConnection(apiBase: string, apiKey: string): Promise<ConnectionTestResult> {
  return fetchJson<ConnectionTestResult>(apiBase, "/api/setup/test/tmdb", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(buildTmdbConnectionTestPayload(apiKey)),
  });
}
