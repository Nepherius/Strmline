<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { onMount } from "svelte";

  import {
    checkLibraryHealth,
    deleteClassificationOverride,
    loadClassificationOverrides,
    loadLibraryDiagnostics,
    loadLibraryEntries,
    removeLibraryEntry,
    refreshLibraryEntryMetadata,
    saveClassificationOverride,
    updateLibraryEntryTmdbId,
    type ClassificationOverride,
    type LibraryHealthCheckResult,
    type LibraryPageRequest,
  } from "$lib/api/library";
  import { loadSetupStatus } from "$lib/api/setup";
  import { loadOperationsMetrics, type OperationsMetrics } from "$lib/api/operations";
  import { loadWatchlist, removeTitleFromWatchlist, type WatchlistItem } from "$lib/api/watchlist";
  import {
    dismissSyncError,
    loadSyncStatus,
    runSyncNow,
    type SyncRunResult,
    type SyncStatus,
  } from "$lib/api/sync";
  import {
    categoryLabels,
    filterFiles,
    sortFiles,
    type LibraryCategory,
    type LibraryDisplayCategory,
    type LibraryDuplicateGroup,
    type LibraryEntry,
    type LibraryFile,
    type LibraryValidation,
    type SortDirection,
    type SortKey,
  } from "$lib/domain/library/summary";
  import AppShell from "$lib/components/ui/AppShell.svelte";
  import AppNavigation from "$lib/components/ui/AppNavigation.svelte";
  import DuplicateGroupsPanel from "$lib/features/dashboard/components/DuplicateGroupsPanel.svelte";
  import LibraryMediaGrid from "$lib/features/dashboard/components/LibraryMediaGrid.svelte";
  import MetricCard from "$lib/components/ui/MetricCard.svelte";
  import MetricGrid from "$lib/components/ui/MetricGrid.svelte";
  import Notice from "$lib/components/ui/Notice.svelte";
  import PageHeader from "$lib/components/ui/PageHeader.svelte";
  import SyncErrorsPanel from "$lib/features/dashboard/components/SyncErrorsPanel.svelte";
  import TextField from "$lib/components/ui/TextField.svelte";
  import UiButton from "$lib/components/ui/UiButton.svelte";

  const categories: (LibraryDisplayCategory | "all")[] = [
    "all",
    "movies",
    "shows",
    "anime",
    "watchlist",
  ];
  const pageSize = 50;

  let category: LibraryDisplayCategory | "all" = "all";
  let query = "";
  let sortKey: SortKey = "title";
  let sortDirection: SortDirection = "asc";
  let libraryEntries: LibraryEntry[] = [];
  let libraryLoaded = false;
  let loadingEntries = false;
  let loadingMoreEntries = false;
  let totalLibraryMatches = 0;
  let totalFiles = 0;
  let categoryCounts: Record<LibraryCategory, number> = {
    movies: 0,
    shows: 0,
    anime: 0,
  };
  let hasMoreEntries = false;
  let nextCursor: string | null = null;
  let pageKey = "";
  let requestSequence = 0;
  let reloadTimer: ReturnType<typeof setTimeout> | undefined;
  let diagnosticsTimer: ReturnType<typeof setTimeout> | undefined;
  let operationsTimer: ReturnType<typeof setInterval> | undefined;
  let loading = false;
  let syncing = false;
  let checkingHealth = false;
  let error = "";
  let removalWarning = "";
  let removalNoticeVariant: "success" | "warning" = "success";
  let syncResult: SyncRunResult | null = null;
  let healthResult: LibraryHealthCheckResult | null = null;
  let syncStatus: SyncStatus | null = null;
  let operationsMetrics: OperationsMetrics | null = null;
  let validation: LibraryValidation | null = null;
  let duplicateGroups: LibraryDuplicateGroup[] = [];
  let duplicateCount = 0;
  let classificationOverrides: ClassificationOverride[] = [];
  let watchlistItems: WatchlistItem[] = [];
  let pendingClassificationKey = "";
  let removingEntryKey = "";
  let refreshingMetadataKey = "";
  let updatingTmdbKey = "";
  let dismissingErrorId: number | null = null;

  $: watchlistEntries = filterFiles(
    watchlistItems.map(watchlistEntry),
    query,
    category === "watchlist" ? "watchlist" : "all",
  );
  $: visibleEntries =
    category === "watchlist"
      ? sortFiles(watchlistEntries, sortKey, sortDirection)
      : category === "all"
        ? sortFiles([...libraryEntries, ...watchlistEntries], sortKey, sortDirection)
        : libraryEntries;
  $: displayedTitleCount =
    category === "watchlist"
      ? watchlistEntries.length
      : totalLibraryMatches + (category === "all" ? watchlistEntries.length : 0);
  $: pageKey = [query.trim(), category, sortKey, sortDirection].join("\u0000");

  onMount(() => {
    void routeToSetupOrLoadDashboard();
    return () => {
      if (reloadTimer) clearTimeout(reloadTimer);
      if (diagnosticsTimer) clearTimeout(diagnosticsTimer);
      if (operationsTimer) clearInterval(operationsTimer);
      requestSequence += 1;
    };
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
      const [nextPage, nextSyncStatus, nextOverrides, nextWatchlist] = await Promise.all([
        loadLibraryEntries(libraryPageRequest(null)),
        loadSyncStatus(),
        loadClassificationOverrides(),
        loadWatchlist(),
      ]);
      applyLibraryPage(nextPage, false);
      syncStatus = nextSyncStatus;
      classificationOverrides = nextOverrides;
      watchlistItems = nextWatchlist;
      libraryLoaded = true;
      scheduleDiagnosticsLoad();
      await refreshOperationsMetrics();
      scheduleOperationsMetricsRefresh();
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Dashboard unavailable. ${message}`;
    } finally {
      loading = false;
    }
  }

  function libraryPageRequest(cursor: string | null): LibraryPageRequest {
    return {
      ...(cursor === null ? {} : { cursor }),
      limit: pageSize,
      ...(category === "movies" || category === "shows" || category === "anime"
        ? { category }
        : {}),
      query: query.trim(),
      sortKey,
      direction: sortDirection,
      includeOverview: cursor === null,
    };
  }

  function applyLibraryPage(page: Awaited<ReturnType<typeof loadLibraryEntries>>, append: boolean) {
    libraryEntries = append ? [...libraryEntries, ...page.entries] : page.entries;
    if (page.total !== null) totalLibraryMatches = page.total;
    if (page.total_files !== null) totalFiles = page.total_files;
    if (page.category_counts !== null) categoryCounts = page.category_counts;
    hasMoreEntries = page.has_more;
    nextCursor = page.next_cursor;
  }

  function scheduleLibraryReload() {
    if (!libraryLoaded) return;
    if (reloadTimer) clearTimeout(reloadTimer);
    reloadTimer = setTimeout(() => {
      void loadFirstLibraryPage();
    }, 250);
  }

  async function loadFirstLibraryPage() {
    const requestedKey = pageKey;
    if (category === "watchlist") {
      libraryEntries = [];
      totalLibraryMatches = 0;
      hasMoreEntries = false;
      nextCursor = null;
      return;
    }
    const requestId = ++requestSequence;
    loadingEntries = true;
    try {
      const page = await loadLibraryEntries(libraryPageRequest(null));
      if (requestId !== requestSequence || requestedKey !== pageKey) return;
      applyLibraryPage(page, false);
    } catch (caughtError) {
      if (requestId !== requestSequence) return;
      error = caughtError instanceof Error ? caughtError.message : "Library search failed.";
    } finally {
      if (requestId === requestSequence) loadingEntries = false;
    }
  }

  async function loadMoreLibraryEntries() {
    if (
      loadingEntries ||
      loadingMoreEntries ||
      !hasMoreEntries ||
      nextCursor === null ||
      category === "watchlist"
    )
      return;
    const requestId = requestSequence;
    const requestedKey = pageKey;
    loadingMoreEntries = true;
    try {
      const page = await loadLibraryEntries(libraryPageRequest(nextCursor));
      if (requestId !== requestSequence || requestedKey !== pageKey) return;
      applyLibraryPage(page, true);
    } catch (caughtError) {
      if (requestId !== requestSequence) return;
      error = caughtError instanceof Error ? caughtError.message : "More titles could not load.";
    } finally {
      if (requestId === requestSequence) loadingMoreEntries = false;
    }
  }

  function scheduleDiagnosticsLoad() {
    if (diagnosticsTimer) clearTimeout(diagnosticsTimer);
    diagnosticsTimer = setTimeout(() => {
      void loadDiagnostics();
    }, 300);
  }

  async function loadDiagnostics() {
    try {
      const diagnostics = await loadLibraryDiagnostics();
      validation = diagnostics;
      duplicateGroups = diagnostics.duplicate_groups;
      duplicateCount = diagnostics.duplicate_file_count;
    } catch {
      // Diagnostics are supplementary and must not block a large library from rendering.
    }
  }

  async function refreshOperationsMetrics() {
    try {
      operationsMetrics = await loadOperationsMetrics();
    } catch {
      // Operational metrics are supplementary and must not block the dashboard.
    }
  }

  function scheduleOperationsMetricsRefresh() {
    if (operationsTimer) clearInterval(operationsTimer);
    operationsTimer = setInterval(() => {
      void refreshOperationsMetrics();
    }, 15_000);
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

  async function runHealthCheck() {
    if (checkingHealth) return;
    checkingHealth = true;
    error = "";
    healthResult = null;
    try {
      healthResult = await checkLibraryHealth();
      await loadFirstLibraryPage();
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Health check failed. ${message}`;
    } finally {
      checkingHealth = false;
    }
  }

  function sortBy(nextSortKey: SortKey) {
    if (sortKey === nextSortKey) {
      sortDirection = sortDirection === "asc" ? "desc" : "asc";
    } else {
      sortKey = nextSortKey;
      sortDirection = "asc";
    }
    scheduleLibraryReload();
  }

  function selectCategory(nextCategory: LibraryDisplayCategory | "all") {
    if (category === nextCategory) return;
    category = nextCategory;
    scheduleLibraryReload();
  }

  async function removeEntry(entry: LibraryEntry) {
    if (entry.category === "watchlist") return;
    const mediaItemId = entry.media_item_id;
    if (!mediaItemId) {
      error = "Remove failed. This entry has no stable media identity.";
      return;
    }
    if (removingEntryKey) return;
    const confirmed = window.confirm(
      `Remove "${entry.title}" from Strmline and TorBox? This cannot be undone from Strmline.`,
    );
    if (!confirmed) return;
    removingEntryKey = entry.key;
    error = "";
    removalWarning = "";
    try {
      const result = await removeLibraryEntry({
        category: entry.category,
        title: entry.title,
        relative_path: entry.relative_path,
        media_item_id: mediaItemId,
      });
      syncResult = null;
      if (result.ok) {
        await loadDashboard();
        removalNoticeVariant =
          result.torbox_removal_failed || result.auto_sync_status !== "success"
            ? "warning"
            : "success";
        removalWarning = result.message;
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
    if (!entry.media_item_id) {
      error = "Metadata refresh failed. This entry has no stable media identity.";
      return;
    }
    if (refreshingMetadataKey) return;
    refreshingMetadataKey = entry.key;
    error = "";
    syncResult = null;
    try {
      const result = await refreshLibraryEntryMetadata({
        category: entry.category,
        relative_path: entry.relative_path,
        media_item_id: entry.media_item_id,
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

  async function updateEntryTmdbId(entry: LibraryEntry, tmdbId: number) {
    if (entry.category === "watchlist") return;
    if (!entry.media_item_id) {
      error = "TMDB ID update failed. This entry has no stable media identity.";
      return;
    }
    if (updatingTmdbKey) return;
    updatingTmdbKey = entry.key;
    error = "";
    syncResult = null;
    try {
      const result = await updateLibraryEntryTmdbId({
        category: entry.category,
        relative_path: entry.relative_path,
        tmdb_id: tmdbId,
        media_item_id: entry.media_item_id,
      });
      if (!result.ok) {
        throw new Error(result.message);
      }
      await loadDashboard();
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `TMDB ID update failed. ${message}`;
      throw caughtError;
    } finally {
      updatingTmdbKey = "";
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
    if (!entry.media_item_id) {
      error = "Move failed. This entry has no stable media identity.";
      return;
    }
    if (pendingClassificationKey) return;
    pendingClassificationKey = entry.key;
    syncing = true;
    error = "";
    syncResult = null;
    try {
      const currentOverride = overrideForEntry(entry);
      if (currentOverride?.source_category === targetCategory) {
        await deleteClassificationOverride({ media_item_id: entry.media_item_id });
      } else if (targetCategory !== entry.category) {
        await saveClassificationOverride({
          media_item_id: entry.media_item_id,
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
    if (!entry.media_item_id) {
      error = "Reset failed. This entry has no stable media identity.";
      return;
    }
    if (pendingClassificationKey) return;
    pendingClassificationKey = entry.key;
    syncing = true;
    error = "";
    syncResult = null;
    try {
      const currentOverride = overrideForEntry(entry);
      if (!currentOverride) return;
      await deleteClassificationOverride({ media_item_id: entry.media_item_id });
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

  async function removeWatchlistEntry(entry: LibraryEntry) {
    if (
      entry.category !== "watchlist" ||
      entry.tmdb_id == null ||
      entry.media_type === undefined ||
      removingEntryKey
    )
      return;
    removingEntryKey = entry.key;
    error = "";
    try {
      await removeTitleFromWatchlist(entry.media_type, entry.tmdb_id);
      watchlistItems = watchlistItems.filter(
        (item) => item.media_type !== entry.media_type || item.tmdb_id !== entry.tmdb_id,
      );
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Could not remove watchlist entry. ${message}`;
    } finally {
      removingEntryKey = "";
    }
  }

  function searchWatchlistEntry(entry: LibraryEntry) {
    const tmdbParam = entry.tmdb_id == null ? "" : `&tmdb_id=${String(entry.tmdb_id)}`;
    const mediaTypeParam = entry.media_type ? `&media_type=${entry.media_type}` : "";
    const searchPath: `/search?${string}` = `/search?q=${encodeURIComponent(entry.title)}${tmdbParam}${mediaTypeParam}`;
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
      media_type: item.media_type,
      imdb_id: item.imdb_id,
      year: item.year,
      overview: item.overview,
    };
  }

  $: recentErrors = syncStatus?.recent_errors ?? [];
  $: lastAutoSyncLabel = formatLastAutoSync(syncStatus?.last_auto_run ?? null);

  function formatDateTime(value: string | null): string {
    if (!value) return "Not finished";
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  }

  function formatLastAutoSync(run: SyncStatus["last_auto_run"]): string {
    if (run === null) return "Never";
    return formatDateTime(run.finished_at ?? run.started_at);
  }

  function issueKey(issue: { code: string; relative_path: string | null }, index: number): string {
    return `${issue.code}-${issue.relative_path ?? String(index)}`;
  }
</script>

<svelte:head>
  <title>Strmline</title>
</svelte:head>

<AppShell>
  <PageHeader ariaLabel="Strmline controls" title="Library dashboard">
    <svelte:fragment slot="actions">
      <form on:submit|preventDefault={runHealthCheck}>
        <UiButton type="submit" disabled={loading || syncing || checkingHealth}>
          {checkingHealth ? "Checking health" : "Check health"}
        </UiButton>
      </form>
      <form on:submit|preventDefault={runManualSync}>
        <UiButton type="submit" disabled={loading || syncing || checkingHealth}>
          {syncing ? "Syncing" : "Run sync"}
        </UiButton>
      </form>
      <AppNavigation />
    </svelte:fragment>
  </PageHeader>

  {#if error}
    <Notice variant="error" resetKey={error}>{error}</Notice>
  {/if}

  {#if removalWarning}
    <Notice variant={removalNoticeVariant} resetKey={removalWarning}>{removalWarning}</Notice>
  {/if}

  {#if syncResult}
    <Notice variant="success" resetKey={String(syncResult.sync_run_id)}
      >Sync #{syncResult.sync_run_id} completed. Library refreshed.</Notice
    >
  {/if}

  {#if healthResult}
    <Notice variant="success" resetKey={healthResult.checked_at}
      >Health checked for {healthResult.checked_entries} files: {healthResult.ready} ready,
      {healthResult.recoverable} recoverable, {healthResult.unavailable} unavailable, and
      {healthResult.unknown} unknown.</Notice
    >
  {/if}

  <section class="sync-summary" aria-label="Sync summary">
    <span>Last auto sync</span>
    <strong>{lastAutoSyncLabel}</strong>
  </section>

  <SyncErrorsPanel errors={recentErrors} {dismissingErrorId} onDismiss={dismissRecentError} />

  {#if libraryLoaded}
    <MetricGrid ariaLabel="Library status" columns={6}>
      <MetricCard label="Total files" value={totalFiles} />
      <MetricCard label="Movies" value={categoryCounts.movies} />
      <MetricCard label="Shows" value={categoryCounts.shows} />
      <MetricCard label="Anime" value={categoryCounts.anime} />
      <MetricCard label="Watchlist" value={watchlistItems.length} />
      <MetricCard
        label="Duplicate files"
        value={duplicateCount}
        variant={duplicateCount > 0 ? "warn" : "default"}
      />
    </MetricGrid>

    {#if operationsMetrics}
      <div class="operations-heading">
        <h2>TorBox operations</h2>
        <span>Since restart</span>
      </div>
      <MetricGrid ariaLabel="TorBox operational metrics" columns={6}>
        <MetricCard label="API calls" value={operationsMetrics.torbox.requests_total} />
        <MetricCard
          label="Last minute"
          value={`${String(operationsMetrics.torbox.calls_last_minute)} / ${String(operationsMetrics.torbox.request_budget_per_minute)}`}
        />
        <MetricCard
          label="429 responses"
          value={operationsMetrics.torbox.responses_429}
          variant={operationsMetrics.torbox.responses_429 > 0 ? "warn" : "default"}
        />
        <MetricCard label="Resolver cache hits" value={operationsMetrics.resolver.cache_hits} />
        <MetricCard
          label="Recoveries ready"
          value={operationsMetrics.resolver.recovery_succeeded}
          variant={operationsMetrics.resolver.recovery_succeeded > 0 ? "ready" : "default"}
        />
        <MetricCard
          label="Recoveries failed"
          value={operationsMetrics.resolver.recovery_failed}
          variant={operationsMetrics.resolver.recovery_failed > 0 ? "warn" : "default"}
        />
      </MetricGrid>
    {/if}

    <section class="workbench" aria-label="Generated library browser">
      <div class="filters">
        <TextField
          bind:value={query}
          label="Search"
          placeholder="Title"
          onInput={scheduleLibraryReload}
        />
        <div class="segments" aria-label="Category filter">
          {#each categories as item (item)}
            <button
              type="button"
              class:active={category === item}
              on:click={() => {
                selectCategory(item);
              }}
            >
              {item === "all" ? "All" : categoryLabels[item]}
            </button>
          {/each}
        </div>
      </div>

      <div class="collection-heading">
        <div>
          <span>Collection</span>
          <strong>{displayedTitleCount} titles</strong>
          <small>{visibleEntries.length} loaded</small>
        </div>
        <button
          type="button"
          title="Sort by title"
          aria-label="Sort by title"
          on:click={() => {
            sortBy("title");
          }}>↕</button
        >
      </div>

      <LibraryMediaGrid
        entries={visibleEntries}
        overrides={classificationOverrides}
        disabled={loading || syncing || checkingHealth}
        {checkingHealth}
        {pendingClassificationKey}
        {removingEntryKey}
        {refreshingMetadataKey}
        {updatingTmdbKey}
        onMove={moveEntry}
        onReset={resetEntryClassification}
        onRemove={removeEntry}
        onRefresh={refreshEntryMetadata}
        onUpdateTmdb={updateEntryTmdbId}
        onRemoveWatchlist={removeWatchlistEntry}
        onSearchWatchlist={searchWatchlistEntry}
        hasMore={hasMoreEntries && category !== "watchlist"}
        loadingMore={loadingMoreEntries}
        onNeedMore={loadMoreLibraryEntries}
      />

      {#if loadingEntries}
        <p class="page-loading" aria-live="polite">Loading titles…</p>
      {/if}

      {#if validation && !validation.ok}
        <section class="curation" aria-label="Library checks">
          <div class="section-heading">
            <h2>Library checks</h2>
            <span>Needs attention</span>
          </div>
          <div class="issue-list">
            {#each [...validation.errors, ...validation.warnings].slice(0, 8) as issue, index (issueKey(issue, index))}
              <article class:error-issue={validation.errors.includes(issue)}>
                <strong>{issue.message}</strong>
                {#if issue.relative_path}
                  <code>{issue.relative_path}</code>
                {/if}
              </article>
            {/each}
          </div>
        </section>
      {/if}

      {#if duplicateGroups.length > 0}
        <DuplicateGroupsPanel
          groups={duplicateGroups.slice(0, 6)}
          disabled={loading || syncing}
          removingKey={removingEntryKey}
          onHideFile={hideDuplicateFile}
        />
      {/if}
    </section>
  {:else if !loading}
    <Notice>No library summary loaded.</Notice>
  {/if}
</AppShell>

<style>
  :global(body) {
    background: #151815;
    color: #f8f5ed;
  }

  :global(main.shell .topbar) {
    border-color: #354039;
  }

  :global(main.shell .topbar .eyebrow),
  :global(main.shell .topbar h1) {
    color: #f8f5ed;
  }

  :global(main.shell .app-nav a),
  :global(main.shell .logout-btn),
  :global(main.shell .metric) {
    border-color: #3b4840;
    background: #202620;
    color: #f8f5ed;
  }

  :global(main.shell .app-nav a.active) {
    border-color: #3e9c7a;
    background: #26795e;
  }

  :global(main.shell .metric span) {
    color: #aab9af;
  }

  :global(main.shell .metric.warn) {
    border-color: #a8773f;
    background: #352b1d;
  }

  h2 {
    margin: 0;
    font-size: 15px;
  }

  .operations-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-top: 22px;
    color: #f8f5ed;
  }

  .operations-heading span {
    color: #aab9af;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
  }

  code {
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
    font-size: 12px;
  }

  .sync-summary {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 14px;
    color: #aab9af;
    font-size: 13px;
  }

  .sync-summary span {
    font-weight: 800;
    text-transform: uppercase;
    color: #f8f5ed;
  }

  .workbench {
    margin-top: 18px;
  }

  .curation {
    display: grid;
    gap: 10px;
    margin-top: 22px;
    border-top: 1px solid #354039;
    border-bottom: 1px solid #354039;
    border-radius: 6px;
    padding: 16px 0;
  }

  .section-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }

  .section-heading span {
    border: 1px solid #a8773f;
    border-radius: 999px;
    padding: 3px 9px;
    background: #352b1d;
    color: #ffdca1;
    font-size: 12px;
    font-weight: 800;
  }

  .issue-list {
    display: grid;
    gap: 8px;
  }

  .issue-list article {
    display: grid;
    gap: 6px;
    border: 1px solid #a8773f;
    border-radius: 6px;
    padding: 10px;
    background: #2a251d;
  }

  .issue-list article.error-issue {
    border-color: #a35a51;
    background: #32201f;
  }

  .filters {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 14px;
    margin-bottom: 18px;
  }

  .filters :global(label) {
    color: #aab9af;
  }

  .filters :global(input) {
    border-color: #3b4840;
    background: #202620;
    color: #f8f5ed;
  }

  .segments {
    display: flex;
    gap: 8px;
  }

  .segments button {
    height: 38px;
    border: 1px solid #3b4840;
    border-radius: 6px;
    padding: 0 14px;
    background: #202620;
    color: #dbe6dd;
    cursor: pointer;
    font-weight: 700;
  }

  .segments button.active {
    border-color: #3e9c7a;
    background: #26795e;
    color: #ffffff;
  }

  .collection-heading {
    display: flex;
    align-items: end;
    justify-content: space-between;
    margin-bottom: 12px;
  }

  .collection-heading div {
    display: grid;
    gap: 2px;
  }

  .collection-heading span {
    color: #aab9af;
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
  }

  .collection-heading strong {
    color: #f8f5ed;
    font-size: 18px;
  }

  .collection-heading small,
  .page-loading {
    color: #aab9af;
    font-size: 12px;
  }

  .page-loading {
    margin: 12px 0;
    text-align: center;
  }

  .collection-heading button {
    display: grid;
    width: 34px;
    height: 34px;
    place-items: center;
    border: 1px solid #3b4840;
    border-radius: 6px;
    padding: 0;
    background: #202620;
    color: #dbe6dd;
    cursor: pointer;
    font-size: 18px;
  }

  @media (max-width: 860px) {
    .filters {
      align-items: stretch;
      flex-direction: column;
    }

    .segments {
      flex-wrap: wrap;
    }
  }
</style>
