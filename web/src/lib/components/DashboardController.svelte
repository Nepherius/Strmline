<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { onMount } from "svelte";

  import { loadLibrarySummary, loadLibraryValidation } from "$lib/libraryApi";
  import { loadSetupStatus } from "$lib/setupApi";
  import { loadSyncStatus, runSyncNow, type SyncRunResult, type SyncStatus } from "$lib/syncApi";
  import {
    duplicateFileCount,
    filterFiles,
    sortFiles,
    type LibraryCategory,
    type LibrarySummary,
    type LibraryValidation,
    type SortDirection,
    type SortKey,
    validationIssueCount,
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
  let validation: LibraryValidation | null = null;

  $: visibleFiles = summary
    ? sortFiles(filterFiles(summary.files, query, category), sortKey, sortDirection)
    : [];
  $: duplicateCount = summary ? duplicateFileCount(summary) : 0;
  $: validationIssues = validation ? validationIssueCount(validation) : 0;

  onMount(() => {
    void routeToSetupOrLoadDashboard();
  });

  async function routeToSetupOrLoadDashboard() {
    loading = true;
    error = "";
    try {
      const status = await loadSetupStatus();
      if (!status.configured) {
        await goto(resolve("/setup?required=1"));
        return;
      }
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Setup status unavailable. ${message}`;
      loading = false;
      return;
    }
    await loadDashboard();
  }

  async function loadDashboard() {
    loading = true;
    error = "";
    try {
      const [nextSummary, nextValidation, nextSyncStatus] = await Promise.all([
        loadLibrarySummary(),
        loadLibraryValidation(),
        loadSyncStatus(),
      ]);
      summary = nextSummary;
      validation = nextValidation;
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
  {validation}
  {validationIssues}
  {visibleFiles}
  onRefresh={loadDashboard}
  onRunSync={runManualSync}
  onSort={sortBy}
/>
