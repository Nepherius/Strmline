import { fetchJson } from "$lib/api";
import type { LibrarySummary } from "$lib/librarySummary";

export function loadLibrarySummary(): Promise<LibrarySummary> {
  return fetchJson<LibrarySummary>("/api/library/summary");
}
