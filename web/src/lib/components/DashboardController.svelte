<script lang="ts">
  import { onMount } from "svelte";

  import { loadLibrarySummary } from "$lib/libraryApi";
  import { loadSyncStatus, runSyncNow, type SyncRunResult, type SyncStatus } from "$lib/syncApi";
  import {
    duplicateFileCount,
    filterFiles,
    sortFiles,
    type LibraryCategory,
    type LibrarySummary,
    type SortDirection,
    type SortKey,
  } from "$lib/librarySummary";

  import DashboardView from "./DashboardView.svelte";

  const categories: (LibraryCategory | "all")[] = ["all", "movies", "shows", "anime"];

  let category: LibraryCategory | "all" = "all";
  let query = "";
  let sortKey: SortKey = "title";
  let sortDirection: SortDirection = "asc";
  let summary: LibrarySummary | null = null;
  let loading = false;
  let syncing = false;
  let error = "";
  let syncResult: SyncRunResult | null = null;
  let syncStatus: SyncStatus | null = null;

  $: visibleFiles = summary
    ? sortFiles(filterFiles(summary.files, query, category), sortKey, sortDirection)
    : [];
  $: duplicateCount = summary ? duplicateFileCount(summary) : 0;

  onMount(() => {
    void loadDashboard();
  });

  async function loadDashboard() {
    loading = true;
    error = "";
    try {
      const [nextSummary, nextSyncStatus] = await Promise.all([
        loadLibrarySummary(),
        loadSyncStatus(),
      ]);
      summary = nextSummary;
      syncStatus = nextSyncStatus;
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Dashboard unavailable. ${message}`;
    } finally {
      loading = false;
    }
  }

  async function runManualSync() {
    syncing = true;
    error = "";
    syncResult = null;
    try {
      syncResult = await runSyncNow();
      await loadDashboard();
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Sync failed. ${message}`;
    } finally {
      syncing = false;
    }
  }

  function sortBy(nextSortKey: SortKey) {
    if (sortKey === nextSortKey) {
      sortDirection = sortDirection === "asc" ? "desc" : "asc";
      return;
    }
    sortKey = nextSortKey;
    sortDirection = "asc";
  }
</script>

<DashboardView
  bind:category
  bind:query
  {categories}
  {duplicateCount}
  {error}
  {loading}
  {syncing}
  {summary}
  {syncResult}
  {syncStatus}
  {visibleFiles}
  onRefresh={loadDashboard}
  onRunSync={runManualSync}
  onSort={sortBy}
/>
