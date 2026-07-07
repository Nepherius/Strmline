import { fetchJson, fetchNoContent } from "$lib/api/client";
import type {
  LibraryCategory,
  LibrarySummary,
  LibraryValidation,
} from "$lib/domain/library/summary";

export interface ClassificationOverride {
  source_category: LibraryCategory;
  source_prefix: string;
  title: string;
  target_category: LibraryCategory;
  target_prefix: string;
}

export interface ClassificationOverridePayload {
  source_category: LibraryCategory;
  source_prefix: string;
  title: string;
  target_category: LibraryCategory;
}

export interface ClassificationOverrideDeletePayload {
  source_category: LibraryCategory;
  source_prefix: string;
}

export interface RemoveLibraryEntryPayload {
  category: string;
  title: string;
  relative_path: string;
  remove_torbox?: boolean;
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

export function loadClassificationOverrides(): Promise<ClassificationOverride[]> {
  return fetchJson<ClassificationOverride[]>("/api/library/classification-overrides");
}

export function saveClassificationOverride(
  payload: ClassificationOverridePayload,
): Promise<ClassificationOverride> {
  return fetchJson<ClassificationOverride>("/api/library/classification-overrides", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function deleteClassificationOverride(
  payload: ClassificationOverrideDeletePayload,
): Promise<void> {
  return fetchNoContent("/api/library/classification-overrides", {
    method: "DELETE",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
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
