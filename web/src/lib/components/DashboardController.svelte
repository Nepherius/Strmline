<script lang="ts">
  import { onMount } from "svelte";

  import { loadLibrarySummary } from "$lib/libraryApi";
  import { runSyncNow, type SyncRunResult } from "$lib/syncApi";
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

  let apiBase = "http://localhost:8000";
  let category: LibraryCategory | "all" = "all";
  let query = "";
  let sortKey: SortKey = "title";
  let sortDirection: SortDirection = "asc";
  let summary: LibrarySummary | null = null;
  let loading = false;
  let syncing = false;
  let error = "";
  let syncResult: SyncRunResult | null = null;

  $: visibleFiles = summary
    ? sortFiles(filterFiles(summary.files, query, category), sortKey, sortDirection)
    : [];
  $: duplicateCount = summary ? duplicateFileCount(summary) : 0;

  onMount(() => {
    const savedApiBase = window.localStorage.getItem("strmline-api-base");
    if (savedApiBase) {
      apiBase = savedApiBase;
    }
    void loadSummary();
  });

  async function loadSummary() {
    loading = true;
    error = "";
    try {
      summary = await loadLibrarySummary(apiBase);
      window.localStorage.setItem("strmline-api-base", apiBase);
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Library summary unavailable. ${message}`;
    } finally {
      loading = false;
    }
  }

  async function runManualSync() {
    syncing = true;
    error = "";
    syncResult = null;
    try {
      syncResult = await runSyncNow(apiBase);
      await loadSummary();
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
  {visibleFiles}
  onRefresh={loadSummary}
  onRunSync={runManualSync}
  onSort={sortBy}
/>
