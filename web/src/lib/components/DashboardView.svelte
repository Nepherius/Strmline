<script lang="ts">
  import AppShell from "$lib/components/ui/AppShell.svelte";
  import MetricCard from "$lib/components/ui/MetricCard.svelte";
  import MetricGrid from "$lib/components/ui/MetricGrid.svelte";
  import Notice from "$lib/components/ui/Notice.svelte";
  import PageHeader from "$lib/components/ui/PageHeader.svelte";
  import TextField from "$lib/components/ui/TextField.svelte";
  import UiButton from "$lib/components/ui/UiButton.svelte";
  import UiLink from "$lib/components/ui/UiLink.svelte";
  import {
    categoryLabels,
    type LibraryCategory,
    type LibraryEntry,
    type LibrarySummary,
    type LibraryValidation,
    type SortKey,
  } from "$lib/librarySummary";
  import type { SyncRunResult, SyncStatus } from "$lib/syncApi";

  export let category: LibraryCategory | "all";
  export let query: string;
  export let categories: (LibraryCategory | "all")[];
  export let duplicateCount: number;
  export let error: string;
  export let loading: boolean;
  export let syncing: boolean;
  export let summary: LibrarySummary | null;
  export let syncResult: SyncRunResult | null;
  export let syncStatus: SyncStatus | null;
  export let validation: LibraryValidation | null;
  export let validationIssues: number;
  export let visibleEntries: LibraryEntry[];
  export let removingEntryKey: string;
  export let onRefresh: () => Promise<void>;
  export let onRunSync: () => Promise<void>;
  export let onRemoveEntry: (entry: LibraryEntry) => Promise<void>;
  export let onSort: (sortKey: SortKey) => void;

  $: recentErrors = syncStatus?.recent_errors ?? [];

  function formatDateTime(value: string | null): string {
    if (!value) return "Not finished";
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
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
      <UiLink href="/search">Search</UiLink>
      <UiLink href="/setup">Setup</UiLink>
      <form class="refresh-form" on:submit|preventDefault={onRunSync}>
        <UiButton type="submit" disabled={loading || syncing}>
          {syncing ? "Syncing" : "Run sync"}
        </UiButton>
      </form>
      <form class="refresh-form" on:submit|preventDefault={onRefresh}>
        <UiButton type="submit" disabled={loading || syncing}>
          {loading ? "Loading" : "Refresh"}
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

  {#if recentErrors.length > 0}
    <section class="sync-errors" aria-label="Recent sync errors">
      <h2>Recent sync errors</h2>
      <div class="error-list">
        {#each recentErrors as syncError (syncError.id)}
          <article>
            <div>
              <strong>{syncError.phase}</strong>
              <span
                >Run #{syncError.sync_run_id} &middot; {formatDateTime(syncError.created_at)}</span
              >
            </div>
            <p>{syncError.message}</p>
          </article>
        {/each}
      </div>
    </section>
  {/if}

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
        <section class="duplicates" aria-label="Duplicate groups">
          <h2>Duplicate groups</h2>
          <div class="duplicate-list">
            {#each summary.duplicate_groups.slice(0, 6) as group (group.key)}
              <article>
                <strong>{group.files[0]?.title}</strong>
                <span>{group.files.length} files</span>
              </article>
            {/each}
          </div>
        </section>
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
                  <button
                    type="button"
                    class="remove-entry"
                    disabled={removingEntryKey === entry.key || loading || syncing}
                    on:click={() => {
                      void onRemoveEntry(entry);
                    }}
                  >
                    {removingEntryKey === entry.key ? "Removing" : "Remove"}
                  </button>
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

  .refresh-form {
    display: flex;
    align-items: end;
  }

  code {
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
    font-size: 12px;
  }

  .sync-errors {
    display: grid;
    gap: 10px;
    margin-top: 18px;
  }

  .error-list {
    display: grid;
    gap: 8px;
  }

  .error-list article {
    display: grid;
    gap: 8px;
    border: 1px solid #d9b66c;
    border-radius: 6px;
    padding: 10px 12px;
    background: #fff9ea;
  }

  .error-list div {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 8px;
  }

  .error-list strong {
    color: #3d3321;
  }

  .error-list span,
  .error-list p {
    margin: 0;
    color: #765d1d;
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

  .duplicates {
    display: grid;
    gap: 10px;
    margin-bottom: 12px;
  }

  .duplicate-list {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 8px;
  }

  .duplicate-list article {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    border: 1px solid #d9b66c;
    border-radius: 6px;
    padding: 10px;
    background: #fff9ea;
  }

  .duplicate-list span {
    color: #765d1d;
    white-space: nowrap;
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

  .remove-entry {
    height: 30px;
    border: 1px solid #a23a35;
    border-radius: 6px;
    padding: 0 10px;
    background: #fff5f4;
    color: #8e251f;
    cursor: pointer;
    font-weight: 800;
  }

  .remove-entry:disabled {
    cursor: not-allowed;
    opacity: 0.65;
  }

  td:first-child {
    font-weight: 700;
  }

  .empty {
    color: #5b6a61;
    text-align: center;
  }

  @media (max-width: 860px) {
    .refresh-form,
    .filters {
      align-items: stretch;
      flex-direction: column;
    }

    .segments {
      flex-wrap: wrap;
    }
  }
</style>
