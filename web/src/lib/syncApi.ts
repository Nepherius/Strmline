import { fetchJson, fetchNoContent } from "$lib/api";

export interface SyncRunResult {
  sync_run_id: number;
  playback_mode: string;
  library_root: string;
  scanned_files: number;
  written_files: number;
  skipped_files: number;
}

export interface SyncRunStatus {
  id: number;
  status: string;
  source: string;
  started_at: string;
  finished_at: string | null;
  scanned_count: number;
  written_count: number;
  skipped_count: number;
}

export interface SyncError {
  id: number;
  sync_run_id: number;
  phase: string;
  item_ref: string | null;
  message: string;
  created_at: string;
}

export interface SyncStatus {
  last_run: SyncRunStatus | null;
  last_auto_run: SyncRunStatus | null;
  recent_errors: SyncError[];
}

export function runSyncNow(): Promise<SyncRunResult> {
  return fetchJson<SyncRunResult>("/api/sync/run", {
    method: "POST",
  });
}

export function loadSyncStatus(): Promise<SyncStatus> {
  return fetchJson<SyncStatus>("/api/sync/status");
}

export function dismissSyncError(errorId: number): Promise<void> {
  return fetchNoContent(`/api/sync/errors/${String(errorId)}/dismiss`, {
    method: "POST",
  });
}
