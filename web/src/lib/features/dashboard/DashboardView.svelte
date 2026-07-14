<script lang="ts">
  import AppShell from "$lib/components/ui/AppShell.svelte";
  import AppNavigation from "$lib/components/ui/AppNavigation.svelte";
  import DuplicateGroupsPanel from "$lib/features/dashboard/components/DuplicateGroupsPanel.svelte";
  import LibraryMediaGrid from "$lib/features/dashboard/components/LibraryMediaGrid.svelte";
  import SyncErrorsPanel from "$lib/features/dashboard/components/SyncErrorsPanel.svelte";
  import MetricCard from "$lib/components/ui/MetricCard.svelte";
  import MetricGrid from "$lib/components/ui/MetricGrid.svelte";
  import Notice from "$lib/components/ui/Notice.svelte";
  import PageHeader from "$lib/components/ui/PageHeader.svelte";
  import TextField from "$lib/components/ui/TextField.svelte";
  import UiButton from "$lib/components/ui/UiButton.svelte";
  import type { ClassificationOverride } from "$lib/api/library";
  import {
    categoryLabels,
    type LibraryCategory,
    type LibraryEntry,
    type LibraryFile,
    type LibrarySummary,
    type LibraryValidation,
    type SortKey,
  } from "$lib/domain/library/summary";
  import type { SyncRunResult, SyncStatus } from "$lib/api/sync";

  export let category: LibraryCategory | "all";
  export let query: string;
  export let categories: (LibraryCategory | "all")[];
  export let duplicateCount: number;
  export let error: string;
  export let loading: boolean;
  export let syncing: boolean;
  export let summary: LibrarySummary | null;
  export let classificationOverrides: ClassificationOverride[];
  export let syncResult: SyncRunResult | null;
  export let syncStatus: SyncStatus | null;
  export let validation: LibraryValidation | null;
  export let validationIssues: number;
  export let visibleEntries: LibraryEntry[];
  export let dismissingErrorId: number | null;
  export let pendingClassificationKey: string;
  export let removingEntryKey: string;
  export let refreshingMetadataKey: string;
  export let onRunSync: () => Promise<void>;
  export let onRemoveEntry: (entry: LibraryEntry) => Promise<void>;
  export let onRefreshMetadata: (entry: LibraryEntry) => Promise<void>;
  export let onHideDuplicateFile: (file: LibraryFile) => Promise<void>;
  export let onMoveEntry: (entry: LibraryEntry, targetCategory: LibraryCategory) => Promise<void>;
  export let onResetEntryClassification: (entry: LibraryEntry) => Promise<void>;
  export let onDismissSyncError: (errorId: number) => Promise<void>;
  export let onSort: (sortKey: SortKey) => void;

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
      <form on:submit|preventDefault={onRunSync}>
        <UiButton type="submit" disabled={loading || syncing}>
          {syncing ? "Syncing" : "Run sync"}
        </UiButton>
      </form>
      <AppNavigation />
    </svelte:fragment>
  </PageHeader>

  {#if error}
    <Notice variant="error">{error}</Notice>
  {/if}

  {#if syncResult}
    <Notice variant="success">Sync #{syncResult.sync_run_id} completed. Library refreshed.</Notice>
  {/if}

  <section class="sync-summary" aria-label="Sync summary">
    <span>Last auto sync</span>
    <strong>{lastAutoSyncLabel}</strong>
  </section>

  <SyncErrorsPanel errors={recentErrors} {dismissingErrorId} onDismiss={onDismissSyncError} />

  {#if summary}
    <MetricGrid ariaLabel="Library status" columns={6}>
      <MetricCard label="Total files" value={summary.total_files} />
      <MetricCard label="Movies" value={summary.category_counts.movies} />
      <MetricCard label="Shows" value={summary.category_counts.shows} />
      <MetricCard label="Anime" value={summary.category_counts.anime} />
      <MetricCard
        label="Duplicate files"
        value={duplicateCount}
        variant={duplicateCount > 0 ? "warn" : "default"}
      />
      <MetricCard
        label="Curation issues"
        value={validationIssues}
        variant={validationIssues > 0 ? "warn" : "default"}
      />
    </MetricGrid>

    <section class="workbench" aria-label="Generated library browser">
      <div class="filters">
        <TextField bind:value={query} label="Search" placeholder="Title or path" />
        <div class="segments" aria-label="Category filter">
          {#each categories as item (item)}
            <button
              type="button"
              class:active={category === item}
              on:click={() => {
                category = item;
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
          <strong>{visibleEntries.length} titles</strong>
        </div>
        <button
          type="button"
          title="Sort by title"
          aria-label="Sort by title"
          on:click={() => {
            onSort("title");
          }}>↕</button
        >
      </div>

      <LibraryMediaGrid
        entries={visibleEntries}
        overrides={classificationOverrides}
        disabled={loading || syncing}
        {pendingClassificationKey}
        {removingEntryKey}
        {refreshingMetadataKey}
        onMove={onMoveEntry}
        onReset={onResetEntryClassification}
        onRemove={onRemoveEntry}
        onRefresh={onRefreshMetadata}
      />

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

      {#if summary.duplicate_groups.length > 0}
        <DuplicateGroupsPanel
          groups={summary.duplicate_groups.slice(0, 6)}
          disabled={loading || syncing}
          removingKey={removingEntryKey}
          onHideFile={onHideDuplicateFile}
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
