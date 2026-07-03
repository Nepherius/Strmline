<script lang="ts">
  import { onMount } from "svelte";

  import {
    categoryLabels,
    duplicateFileCount,
    filterFiles,
    sortFiles,
    type LibraryCategory,
    type LibrarySummary,
    type SortDirection,
    type SortKey,
  } from "$lib/librarySummary";

  const categories: (LibraryCategory | "all")[] = ["all", "movies", "shows", "anime"];

  let apiBase = "http://localhost:8000";
  let category: LibraryCategory | "all" = "all";
  let query = "";
  let sortKey: SortKey = "title";
  let sortDirection: SortDirection = "asc";
  let summary: LibrarySummary | null = null;
  let loading = false;
  let error = "";

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
      const response = await fetch(`${apiBase.replace(/\/$/, "")}/api/library/summary`);
      if (!response.ok) {
        throw new Error(`API returned ${String(response.status)}`);
      }
      summary = (await response.json()) as LibrarySummary;
      window.localStorage.setItem("strmline-api-base", apiBase);
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Library summary unavailable. ${message}`;
    } finally {
      loading = false;
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

<svelte:head>
  <title>Strmline</title>
</svelte:head>

<main class="shell">
  <section class="topbar" aria-label="Strmline controls">
    <div>
      <p class="eyebrow">Strmline</p>
      <h1>Library dashboard</h1>
    </div>
    <form class="connection" on:submit|preventDefault={loadSummary}>
      <label>
        <span>API</span>
        <input bind:value={apiBase} aria-label="API base URL" />
      </label>
      <button type="submit" disabled={loading}>{loading ? "Loading" : "Refresh"}</button>
    </form>
  </section>

  {#if error}
    <p class="notice error">{error}</p>
  {/if}

  {#if summary}
    <section class="status-grid" aria-label="Library status">
      <div class="metric">
        <span>Total files</span>
        <strong>{summary.total_files}</strong>
      </div>
      <div class="metric">
        <span>Movies</span>
        <strong>{summary.category_counts.movies}</strong>
      </div>
      <div class="metric">
        <span>Shows</span>
        <strong>{summary.category_counts.shows}</strong>
      </div>
      <div class="metric">
        <span>Anime</span>
        <strong>{summary.category_counts.anime}</strong>
      </div>
      <div class:warn={duplicateCount > 0} class="metric">
        <span>Duplicate files</span>
        <strong>{duplicateCount}</strong>
      </div>
    </section>

    <section class="library-root" aria-label="Library root">
      <span>{summary.exists ? "Library root" : "Missing library root"}</span>
      <code>{summary.root ?? "Not configured"}</code>
    </section>

    <section class="workbench" aria-label="Generated library browser">
      <div class="filters">
        <label>
          <span>Search</span>
          <input bind:value={query} placeholder="Title or path" />
        </label>
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
                    sortBy("title");
                  }}>Title</button
                >
              </th>
              <th>
                <button
                  type="button"
                  on:click={() => {
                    sortBy("category");
                  }}>Type</button
                >
              </th>
              <th>
                <button
                  type="button"
                  on:click={() => {
                    sortBy("relative_path");
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
    <p class="notice">No library summary loaded.</p>
  {/if}
</main>

<style>
  :global(body) {
    margin: 0;
    background: #f5f7f6;
    color: #15201b;
    font-family:
      Inter,
      ui-sans-serif,
      system-ui,
      -apple-system,
      BlinkMacSystemFont,
      "Segoe UI",
      sans-serif;
  }

  button,
  input {
    font: inherit;
  }

  .shell {
    box-sizing: border-box;
    min-height: 100vh;
    padding: 24px;
  }

  .topbar {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 20px;
    padding-bottom: 18px;
    border-bottom: 1px solid #d7ded9;
  }

  .eyebrow {
    margin: 0 0 2px;
    color: #5b6a61;
    font-size: 13px;
    font-weight: 700;
    text-transform: uppercase;
  }

  h1,
  h2 {
    margin: 0;
    letter-spacing: 0;
  }

  h1 {
    font-size: 32px;
    line-height: 1.1;
  }

  h2 {
    font-size: 15px;
  }

  .connection {
    display: flex;
    align-items: end;
    gap: 10px;
  }

  label {
    display: grid;
    gap: 6px;
    color: #526057;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
  }

  input {
    box-sizing: border-box;
    min-width: 260px;
    height: 38px;
    border: 1px solid #bcc8c1;
    border-radius: 6px;
    padding: 0 10px;
    background: #ffffff;
    color: #15201b;
  }

  button {
    height: 38px;
    border: 1px solid #1c4333;
    border-radius: 6px;
    padding: 0 14px;
    background: #1f5b42;
    color: #ffffff;
    cursor: pointer;
    font-weight: 700;
  }

  button:disabled {
    cursor: wait;
    opacity: 0.6;
  }

  .notice {
    margin: 18px 0 0;
    border: 1px solid #d7ded9;
    border-radius: 6px;
    padding: 12px;
    background: #ffffff;
  }

  .error {
    border-color: #e1a2a2;
    background: #fff5f4;
    color: #8e251f;
  }

  .status-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(130px, 1fr));
    gap: 10px;
    margin-top: 18px;
  }

  .metric {
    border: 1px solid #d7ded9;
    border-radius: 6px;
    padding: 12px;
    background: #ffffff;
  }

  .metric span {
    display: block;
    color: #5b6a61;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
  }

  .metric strong {
    display: block;
    margin-top: 6px;
    font-size: 26px;
  }

  .metric.warn {
    border-color: #d9b66c;
    background: #fff9ea;
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
    border-color: #bdc8c2;
    background: #ffffff;
    color: #24352d;
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
    .shell {
      padding: 16px;
    }

    .topbar,
    .connection,
    .filters {
      align-items: stretch;
      flex-direction: column;
    }

    .status-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    input {
      min-width: 0;
      width: 100%;
    }

    .segments {
      flex-wrap: wrap;
    }
  }
</style>
