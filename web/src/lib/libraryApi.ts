import { fetchJson } from "$lib/api";
import type { LibrarySummary } from "$lib/librarySummary";

export function loadLibrarySummary(apiBase: string): Promise<LibrarySummary> {
  return fetchJson<LibrarySummary>(apiBase, "/api/library/summary");
}
