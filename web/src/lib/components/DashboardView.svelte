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
    type LibraryFile,
    type LibrarySummary,
    type SortKey,
  } from "$lib/librarySummary";

  export let category: LibraryCategory | "all";
  export let query: string;
  export let categories: (LibraryCategory | "all")[];
  export let duplicateCount: number;
  export let error: string;
  export let loading: boolean;
  export let summary: LibrarySummary | null;
  export let visibleFiles: LibraryFile[];
  export let onRefresh: () => Promise<void>;
  export let onSort: (sortKey: SortKey) => void;
</script>

<svelte:head>
  <title>Strmline</title>
</svelte:head>

<AppShell>
  <PageHeader ariaLabel="Strmline controls" title="Library dashboard">
    <svelte:fragment slot="actions">
      <UiLink href="/setup">Setup</UiLink>
      <form class="refresh-form" on:submit|preventDefault={onRefresh}>
        <UiButton type="submit" disabled={loading}>{loading ? "Loading" : "Refresh"}</UiButton>
      </form>
    </svelte:fragment>
  </PageHeader>

  {#if error}
    <Notice variant="error">{error}</Notice>
  {/if}

  {#if summary}
    <MetricGrid ariaLabel="Library status" columns={5}>
      <MetricCard label="Total files" value={summary.total_files} />
      <MetricCard label="Movies" value={summary.category_counts.movies} />
      <MetricCard label="Shows" value={summary.category_counts.shows} />
      <MetricCard label="Anime" value={summary.category_counts.anime} />
      <MetricCard
        label="Duplicate files"
        value={duplicateCount}
        variant={duplicateCount > 0 ? "warn" : "default"}
      />
    </MetricGrid>

    <section class="library-root" aria-label="Library root">
      <span>{summary.exists ? "Library root" : "Missing library root"}</span>
      <code>{summary.root ?? "Not configured"}</code>
    </section>

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
                  }}>Path</button
                >
              </th>
            </tr>
          </thead>
          <tbody>
            {#each visibleFiles as file (file.relative_path)}
              <tr>
                <td>{file.title}</td>
                <td>{categoryLabels[file.category]}</td>
                <td><code>{file.relative_path}</code></td>
              </tr>
            {:else}
              <tr>
                <td colspan="3" class="empty">No generated files match the current view.</td>
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

  .library-root {
    display: grid;
    gap: 6px;
    margin-top: 12px;
    border: 1px solid #d7ded9;
    border-radius: 6px;
    padding: 12px;
    background: #ffffff;
  }

  .library-root span {
    color: #5b6a61;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
  }

  code {
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
    font-size: 12px;
  }

  .workbench {
    margin-top: 18px;
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
