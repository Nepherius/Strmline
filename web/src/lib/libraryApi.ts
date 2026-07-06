import { fetchJson } from "$lib/api";
import type { LibrarySummary, LibraryValidation } from "$lib/librarySummary";

export interface RemoveLibraryEntryPayload {
  category: string;
  title: string;
  relative_path: string;
}

export interface RemoveLibraryEntryResult {
  ok: boolean;
  message: string;
  removed_files: number;
  removed_torbox_items: number;
}

export function loadLibrarySummary(): Promise<LibrarySummary> {
  return fetchJson<LibrarySummary>("/api/library/summary");
}

export function loadLibraryValidation(): Promise<LibraryValidation> {
  return fetchJson<LibraryValidation>("/api/library/validation");
}

export function removeLibraryEntry(
  payload: RemoveLibraryEntryPayload,
): Promise<RemoveLibraryEntryResult> {
  return fetchJson<RemoveLibraryEntryResult>("/api/library/entries", {
    method: "DELETE",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
}
