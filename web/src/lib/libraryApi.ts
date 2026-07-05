import { fetchJson } from "$lib/api";
import type { LibrarySummary, LibraryValidation } from "$lib/librarySummary";

export function loadLibrarySummary(): Promise<LibrarySummary> {
  return fetchJson<LibrarySummary>("/api/library/summary");
}

export function loadLibraryValidation(): Promise<LibraryValidation> {
  return fetchJson<LibraryValidation>("/api/library/validation");
}
