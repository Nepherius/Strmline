<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { onMount } from "svelte";

  import {
    deleteClassificationOverride,
    loadClassificationOverrides,
    loadLibrarySummary,
    loadLibraryValidation,
    removeLibraryEntry,
    saveClassificationOverride,
    type ClassificationOverride,
  } from "$lib/libraryApi";
  import { loadSetupStatus } from "$lib/setupApi";
  import {
    dismissSyncError,
    loadSyncStatus,
    runSyncNow,
    type SyncRunResult,
    type SyncStatus,
  } from "$lib/syncApi";
  import {
    duplicateFileCount,
    filterFiles,
    sortFiles,
    type LibraryCategory,
    type LibraryEntry,
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
  let classificationOverrides: ClassificationOverride[] = [];
  let pendingClassificationKey = "";
  let removingEntryKey = "";
  let dismissingErrorId: number | null = null;

  $: visibleEntries = summary
    ? sortFiles(filterFiles(summary.entries, query, category), sortKey, sortDirection)
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
      const [nextSummary, nextValidation, nextSyncStatus, nextOverrides] = await Promise.all([
        loadLibrarySummary(),
        loadLibraryValidation(),
        loadSyncStatus(),
        loadClassificationOverrides(),
      ]);
      summary = nextSummary;
      validation = nextValidation;
      syncStatus = nextSyncStatus;
      classificationOverrides = nextOverrides;
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

  async function removeEntry(entry: LibraryEntry) {
    if (removingEntryKey) return;
    const confirmed = window.confirm(
      `Remove "${entry.title}" from Strmline and TorBox? This cannot be undone from Strmline.`,
    );
    if (!confirmed) return;
    removingEntryKey = entry.key;
    error = "";
    try {
      const result = await removeLibraryEntry({
        category: entry.category,
        title: entry.title,
        relative_path: entry.relative_path,
      });
      syncResult = null;
      if (result.ok) {
        await loadDashboard();
      } else {
        error = result.message;
      }
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Remove failed. ${message}`;
    } finally {
      removingEntryKey = "";
    }
  }

  async function moveEntry(entry: LibraryEntry, targetCategory: LibraryCategory) {
    if (pendingClassificationKey) return;
    pendingClassificationKey = entry.key;
    syncing = true;
    error = "";
    syncResult = null;
    try {
      const currentOverride = overrideForEntry(entry);
      if (currentOverride) {
        await deleteMovedPathOverride(entry, currentOverride);
        if (targetCategory === currentOverride.source_category) {
          await deleteClassificationOverride({
            source_category: currentOverride.source_category,
            source_prefix: currentOverride.source_prefix,
          });
        } else {
          await saveClassificationOverride({
            source_category: currentOverride.source_category,
            source_prefix: currentOverride.source_prefix,
            title: currentOverride.title,
            target_category: targetCategory,
          });
        }
      } else if (targetCategory !== entry.category) {
        await saveClassificationOverride({
          source_category: entry.category,
          source_prefix: entry.relative_path,
          title: entry.title,
          target_category: targetCategory,
        });
      }
      syncResult = await runSyncNow();
      await loadDashboard();
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Move failed. ${message}`;
    } finally {
      pendingClassificationKey = "";
      syncing = false;
    }
  }

  async function resetEntryClassification(entry: LibraryEntry) {
    if (pendingClassificationKey) return;
    pendingClassificationKey = entry.key;
    syncing = true;
    error = "";
    syncResult = null;
    try {
      const currentOverride = overrideForEntry(entry);
      if (!currentOverride) return;
      await deleteMovedPathOverride(entry, currentOverride);
      await deleteClassificationOverride({
        source_category: currentOverride.source_category,
        source_prefix: currentOverride.source_prefix,
      });
      syncResult = await runSyncNow();
      await loadDashboard();
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Reset failed. ${message}`;
    } finally {
      pendingClassificationKey = "";
      syncing = false;
    }
  }

  async function dismissRecentError(errorId: number) {
    if (dismissingErrorId !== null) return;
    dismissingErrorId = errorId;
    error = "";
    try {
      await dismissSyncError(errorId);
      syncStatus = await loadSyncStatus();
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Dismiss failed. ${message}`;
    } finally {
      dismissingErrorId = null;
    }
  }

  function overrideForEntry(entry: LibraryEntry): ClassificationOverride | null {
    return (
      classificationOverrides.find((override) => override.target_prefix === entry.relative_path) ??
      classificationOverrides.find((override) => override.source_prefix === entry.relative_path) ??
      null
    );
  }

  async function deleteMovedPathOverride(
    entry: LibraryEntry,
    override: ClassificationOverride,
  ): Promise<void> {
    if (entry.relative_path === override.source_prefix) return;
    await deleteClassificationOverride({
      source_category: entry.category,
      source_prefix: entry.relative_path,
    });
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
  {classificationOverrides}
  {syncResult}
  {syncStatus}
  {validation}
  {validationIssues}
  {visibleEntries}
  {dismissingErrorId}
  {pendingClassificationKey}
  {removingEntryKey}
  onRunSync={runManualSync}
  onSort={sortBy}
  onRemoveEntry={removeEntry}
  onMoveEntry={moveEntry}
  onResetEntryClassification={resetEntryClassification}
  onDismissSyncError={dismissRecentError}
/>
