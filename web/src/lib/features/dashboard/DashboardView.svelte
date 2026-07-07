<script lang="ts">
  import AppShell from "$lib/components/ui/AppShell.svelte";
  import AppNavigation from "$lib/components/ui/AppNavigation.svelte";
  import DuplicateGroupsPanel from "$lib/features/dashboard/components/DuplicateGroupsPanel.svelte";
  import LibraryEntryActions from "$lib/features/dashboard/components/LibraryEntryActions.svelte";
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
  export let onRunSync: () => Promise<void>;
  export let onRemoveEntry: (entry: LibraryEntry) => Promise<void>;
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

  function classificationOverride(entry: LibraryEntry): ClassificationOverride | null {
    return (
      classificationOverrides.find((override) => override.target_prefix === entry.relative_path) ??
      classificationOverrides.find((override) => override.source_prefix === entry.relative_path) ??
      null
    );
  }
</script>

<svelte:head>
  <title>Strmline</title>
</svelte:head>

<AppShell>
  <PageHeader ariaLabel="Strmline controls" title="Library dashboard">
    <svelte:fragment slot="actions">
      <AppNavigation />
      <form on:submit|preventDefault={onRunSync}>
        <UiButton type="submit" disabled={loading || syncing}>
          {syncing ? "Syncing" : "Run sync"}
        </UiButton>
      </form>
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
      {#if validation}
        <section class="curation" aria-label="Library checks">
          <div class="section-heading">
            <h2>Library checks</h2>
            <span class:ready={validation.ok}>
              {validation.ok ? "Ready" : "Needs attention"}
            </span>
          </div>
          {#if validation.errors.length > 0 || validation.warnings.length > 0}
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
          {:else}
            <p class="quiet">Generated paths and STRM URLs match the Jellyfin validation rules.</p>
          {/if}
        </section>
      {/if}

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

      {#if summary.duplicate_groups.length > 0}
        <DuplicateGroupsPanel
          groups={summary.duplicate_groups.slice(0, 6)}
          disabled={loading || syncing}
          removingKey={removingEntryKey}
          onHideFile={onHideDuplicateFile}
        />
      {/if}

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>
                <button
                  type="button"
                  on:click={() => {
                    onSort("title");
                  }}>Title</button
                >
              </th>
              <th>
                <button
                  type="button"
                  on:click={() => {
                    onSort("category");
                  }}>Type</button
                >
              </th>
              <th>
                <button
                  type="button"
                  on:click={() => {
                    onSort("relative_path");
                  }}>Folder</button
                >
              </th>
              <th>Files</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {#each visibleEntries as entry (entry.key)}
              <tr>
                <td>{entry.title}</td>
                <td>{categoryLabels[entry.category]}</td>
                <td><code>{entry.relative_path}</code></td>
                <td>{entry.file_count}</td>
                <td>
                  <LibraryEntryActions
                    {entry}
                    currentOverride={classificationOverride(entry)}
                    disabled={loading || syncing}
                    pending={removingEntryKey === entry.key ||
                      pendingClassificationKey === entry.key}
                    onMove={onMoveEntry}
                    onReset={onResetEntryClassification}
                    onRemove={onRemoveEntry}
                  />
                </td>
              </tr>
            {:else}
              <tr>
                <td colspan="5" class="empty">No generated entries match the current view.</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>
  {:else if !loading}
    <Notice>No library summary loaded.</Notice>
  {/if}
</AppShell>

<style>
  h2 {
    margin: 0;
    letter-spacing: 0;
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
    color: #526057;
    font-size: 13px;
  }

  .sync-summary span {
    font-weight: 800;
    text-transform: uppercase;
    color: #15201b;
  }
  .workbench {
    margin-top: 18px;
  }

  .curation {
    display: grid;
    gap: 10px;
    margin-bottom: 14px;
    border: 1px solid #d7ded9;
    border-radius: 6px;
    padding: 12px;
    background: #ffffff;
  }

  .section-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }

  .section-heading span {
    border: 1px solid #d9b66c;
    border-radius: 999px;
    padding: 3px 9px;
    background: #fff9ea;
    color: #765d1d;
    font-size: 12px;
    font-weight: 800;
  }

  .section-heading span.ready {
    border-color: #9bc9aa;
    background: #f0fff4;
    color: #1f5b42;
  }

  .issue-list {
    display: grid;
    gap: 8px;
  }

  .issue-list article {
    display: grid;
    gap: 6px;
    border: 1px solid #d9b66c;
    border-radius: 6px;
    padding: 10px;
    background: #fff9ea;
  }

  .issue-list article.error-issue {
    border-color: #e1a2a2;
    background: #fff5f4;
  }

  .quiet {
    margin: 0;
    color: #5b6a61;
  }

  .filters {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 14px;
    margin-bottom: 12px;
  }

  .segments {
    display: flex;
    gap: 6px;
  }

  .segments button {
    height: 38px;
    border-color: #bdc8c2;
    border-radius: 6px;
    padding: 0 14px;
    background: #ffffff;
    color: #24352d;
    cursor: pointer;
    font-weight: 700;
  }

  .segments button.active {
    border-color: #1f5b42;
    background: #1f5b42;
    color: #ffffff;
  }

  .table-wrap {
    overflow: auto;
    border: 1px solid #d7ded9;
    border-radius: 6px;
    background: #ffffff;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    min-width: 760px;
  }

  th,
  td {
    border-bottom: 1px solid #e4e9e6;
    padding: 10px 12px;
    text-align: left;
    vertical-align: top;
  }

  th {
    background: #eef3f0;
    color: #4b5b52;
    font-size: 12px;
    text-transform: uppercase;
  }

  th button {
    height: auto;
    border: 0;
    padding: 0;
    background: transparent;
    color: inherit;
  }

  td:first-child {
    font-weight: 700;
  }

  .empty {
    color: #5b6a61;
    text-align: center;
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
