import { fetchJson, fetchNoContent } from "$lib/api/client";
import type {
  LibraryCategory,
  LibraryDiagnostics,
  LibraryEntryPage,
  LibrarySummary,
  LibraryValidation,
} from "$lib/domain/library/summary";

export interface LibraryPageRequest {
  cursor?: string;
  limit?: number;
  category?: LibraryCategory;
  query?: string;
  sortKey?: "title" | "category" | "relative_path";
  direction?: "asc" | "desc";
  includeOverview?: boolean;
}

export interface ClassificationOverride {
  source_category: LibraryCategory;
  source_prefix: string;
  title: string;
  target_category: LibraryCategory;
  target_prefix: string;
}

export interface ClassificationOverridePayload {
  media_item_id: number;
  target_category: LibraryCategory;
}

export interface ClassificationOverrideDeletePayload {
  media_item_id: number;
}

export interface RemoveLibraryEntryPayload {
  category: string;
  title: string;
  relative_path: string;
  media_item_id?: number;
  remove_torbox?: boolean;
}

export interface RemoveLibraryEntryResult {
  ok: boolean;
  message: string;
  removed_files: number;
  removed_torbox_items: number;
  torbox_removal_failed: boolean;
  auto_sync_status: string;
  auto_sync_run_id: number | null;
}

export interface RefreshLibraryEntryMetadataPayload {
  category: LibraryCategory;
  relative_path: string;
  media_item_id: number;
}

export interface RefreshLibraryEntryMetadataResult {
  ok: boolean;
  message: string;
  refreshed_posters: number;
}

export interface UpdateLibraryEntryTmdbIdPayload {
  category: LibraryCategory;
  relative_path: string;
  tmdb_id: number;
  media_item_id: number;
}

export interface UpdateLibraryEntryTmdbIdResult {
  ok: boolean;
  message: string;
  tmdb_id: number;
  refreshed_posters: number;
}

export interface LibraryHealthCheckResult {
  checked_at: string;
  checked_entries: number;
  distinct_hashes: number;
  ready: number;
  recoverable: number;
  unavailable: number;
  unknown: number;
}

export function loadLibrarySummary(): Promise<LibrarySummary> {
  return fetchJson<LibrarySummary>("/api/library/summary");
}

export function loadLibraryEntries(request: LibraryPageRequest = {}): Promise<LibraryEntryPage> {
  const params = new URLSearchParams({
    limit: String(request.limit ?? 50),
    query: request.query ?? "",
    sort_key: request.sortKey ?? "title",
    direction: request.direction ?? "asc",
    include_overview: String(request.includeOverview ?? true),
  });
  if (request.cursor) params.set("cursor", request.cursor);
  if (request.category) params.set("category", request.category);
  return fetchJson<LibraryEntryPage>(`/api/library/entries?${params.toString()}`);
}

export function loadLibraryValidation(): Promise<LibraryValidation> {
  return fetchJson<LibraryValidation>("/api/library/validation");
}

export function loadLibraryDiagnostics(): Promise<LibraryDiagnostics> {
  return fetchJson<LibraryDiagnostics>("/api/library/diagnostics");
}

export function checkLibraryHealth(): Promise<LibraryHealthCheckResult> {
  return fetchJson<LibraryHealthCheckResult>("/api/library/health/check", {
    method: "POST",
  });
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

export function refreshLibraryEntryMetadata(
  payload: RefreshLibraryEntryMetadataPayload,
): Promise<RefreshLibraryEntryMetadataResult> {
  return fetchJson<RefreshLibraryEntryMetadataResult>("/api/library/entries/refresh-metadata", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updateLibraryEntryTmdbId(
  payload: UpdateLibraryEntryTmdbIdPayload,
): Promise<UpdateLibraryEntryTmdbIdResult> {
  return fetchJson<UpdateLibraryEntryTmdbIdResult>("/api/library/entries/tmdb-id", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
}
