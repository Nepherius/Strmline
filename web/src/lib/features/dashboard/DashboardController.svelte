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
    refreshLibraryEntryMetadata,
    saveClassificationOverride,
    type ClassificationOverride,
  } from "$lib/api/library";
  import { loadSetupStatus } from "$lib/api/setup";
  import { loadWatchlist, removeTitleFromWatchlist, type WatchlistItem } from "$lib/api/watchlist";
  import {
    dismissSyncError,
    loadSyncStatus,
    runSyncNow,
    type SyncRunResult,
    type SyncStatus,
  } from "$lib/api/sync";
  import {
    duplicateFileCount,
    filterFiles,
    sortFiles,
    type LibraryCategory,
    type LibraryDisplayCategory,
    type LibraryEntry,
    type LibraryFile,
    type LibrarySummary,
    type LibraryValidation,
    type SortDirection,
    type SortKey,
    validationIssueCount,
  } from "$lib/domain/library/summary";

  import DashboardView from "./DashboardView.svelte";

  const categories: (LibraryDisplayCategory | "all")[] = [
    "all",
    "movies",
    "shows",
    "anime",
    "watchlist",
  ];

  let category: LibraryDisplayCategory | "all" = "all";
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
  let watchlistItems: WatchlistItem[] = [];
  let pendingClassificationKey = "";
  let removingEntryKey = "";
  let refreshingMetadataKey = "";
  let dismissingErrorId: number | null = null;

  $: allEntries = summary
    ? [...summary.entries, ...watchlistItems.map(watchlistEntry)]
    : watchlistItems.map(watchlistEntry);
  $: visibleEntries = summary
    ? sortFiles(filterFiles(allEntries, query, category), sortKey, sortDirection)
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
      const [nextSummary, nextValidation, nextSyncStatus, nextOverrides, nextWatchlist] =
        await Promise.all([
          loadLibrarySummary(),
          loadLibraryValidation(),
          loadSyncStatus(),
          loadClassificationOverrides(),
          loadWatchlist(),
        ]);
      summary = nextSummary;
      validation = nextValidation;
      syncStatus = nextSyncStatus;
      classificationOverrides = nextOverrides;
      watchlistItems = nextWatchlist;
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
    if (entry.category === "watchlist") return;
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

  async function refreshEntryMetadata(entry: LibraryEntry) {
    if (entry.category === "watchlist") return;
    if (refreshingMetadataKey) return;
    refreshingMetadataKey = entry.key;
    error = "";
    syncResult = null;
    try {
      const result = await refreshLibraryEntryMetadata({
        category: entry.category,
        relative_path: entry.relative_path,
      });
      if (!result.ok) {
        error = result.message;
        return;
      }
      await loadDashboard();
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Metadata refresh failed. ${message}`;
    } finally {
      refreshingMetadataKey = "";
    }
  }

  async function hideDuplicateFile(file: LibraryFile) {
    if (removingEntryKey) return;
    const confirmed = window.confirm(
      `Hide "${file.relative_path}" from the generated library? This will not remove it from TorBox.`,
    );
    if (!confirmed) return;
    removingEntryKey = file.relative_path;
    error = "";
    try {
      const result = await removeLibraryEntry({
        category: file.category,
        title: file.title,
        relative_path: file.relative_path,
        remove_torbox: false,
      });
      syncResult = null;
      if (result.ok) {
        await loadDashboard();
      } else {
        error = result.message;
      }
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Hide duplicate failed. ${message}`;
    } finally {
      removingEntryKey = "";
    }
  }

  async function moveEntry(entry: LibraryEntry, targetCategory: LibraryCategory) {
    if (entry.category === "watchlist") return;
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
    if (entry.category === "watchlist") return;
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
    if (entry.category === "watchlist") return null;
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
    if (entry.category === "watchlist") return;
    if (entry.relative_path === override.source_prefix) return;
    await deleteClassificationOverride({
      source_category: entry.category,
      source_prefix: entry.relative_path,
    });
  }

  async function removeWatchlistEntry(entry: LibraryEntry) {
    if (entry.category !== "watchlist" || entry.tmdb_id === undefined || removingEntryKey) return;
    removingEntryKey = entry.key;
    error = "";
    try {
      await removeTitleFromWatchlist(entry.tmdb_id);
      watchlistItems = watchlistItems.filter((item) => item.tmdb_id !== entry.tmdb_id);
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Could not remove watchlist entry. ${message}`;
    } finally {
      removingEntryKey = "";
    }
  }

  function searchWatchlistEntry(entry: LibraryEntry) {
    const tmdbParam = entry.tmdb_id === undefined ? "" : `&tmdb_id=${String(entry.tmdb_id)}`;
    const searchPath: `/search?${string}` = `/search?q=${encodeURIComponent(entry.title)}${tmdbParam}`;
    void goto(resolve(searchPath));
  }

  function watchlistEntry(item: WatchlistItem): LibraryEntry {
    return {
      key: `watchlist/${String(item.id)}`,
      category: "watchlist",
      title: item.title,
      relative_path: "",
      file_count: 0,
      poster_url: item.poster_url,
      watchlist_id: item.id,
      tmdb_id: item.tmdb_id,
      imdb_id: item.imdb_id,
      year: item.year,
      overview: item.overview,
    };
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
  watchlistCount={watchlistItems.length}
  {classificationOverrides}
  {syncResult}
  {syncStatus}
  {validation}
  {validationIssues}
  {visibleEntries}
  {dismissingErrorId}
  {pendingClassificationKey}
  {removingEntryKey}
  {refreshingMetadataKey}
  onRunSync={runManualSync}
  onSort={sortBy}
  onRemoveEntry={removeEntry}
  onRefreshMetadata={refreshEntryMetadata}
  onHideDuplicateFile={hideDuplicateFile}
  onMoveEntry={moveEntry}
  onResetEntryClassification={resetEntryClassification}
  onRemoveWatchlistEntry={removeWatchlistEntry}
  onSearchWatchlistEntry={searchWatchlistEntry}
  onDismissSyncError={dismissRecentError}
/>
