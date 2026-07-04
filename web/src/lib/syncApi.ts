import { fetchJson } from "$lib/api";

export interface SyncRunResult {
  sync_run_id: number;
  playback_mode: string;
  library_root: string;
  scanned_files: number;
  written_files: number;
  skipped_files: number;
}

export function runSyncNow(apiBase: string): Promise<SyncRunResult> {
  return fetchJson<SyncRunResult>(apiBase, "/api/sync/run", {
    method: "POST",
  });
}
