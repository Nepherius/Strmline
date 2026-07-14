<script lang="ts">
  import type { ClassificationOverride } from "$lib/api/library";
  import {
    categoryLabels,
    type LibraryCategory,
    type LibraryEntry,
  } from "$lib/domain/library/summary";

  import LibraryEntryDialog from "./LibraryEntryDialog.svelte";

  export let entries: LibraryEntry[];
  export let overrides: ClassificationOverride[];
  export let disabled = false;
  export let pendingClassificationKey = "";
  export let removingEntryKey = "";
  export let refreshingMetadataKey = "";
  export let onMove: (entry: LibraryEntry, targetCategory: LibraryCategory) => Promise<void>;
  export let onReset: (entry: LibraryEntry) => Promise<void>;
  export let onRemove: (entry: LibraryEntry) => Promise<void>;
  export let onRefresh: (entry: LibraryEntry) => Promise<void>;

  let loadedPosters: Record<string, boolean> = {};
  let failedPosters: Record<string, boolean> = {};
  let selectedEntry: LibraryEntry | null = null;

  function classificationOverride(entry: LibraryEntry): ClassificationOverride | null {
    return (
      overrides.find((override) => override.target_prefix === entry.relative_path) ??
      overrides.find((override) => override.source_prefix === entry.relative_path) ??
      null
    );
  }

  function coverWords(title: string): string[] {
    return title.split(/\s+/).filter(Boolean).slice(0, 4);
  }

  function markPosterLoaded(key: string): void {
    loadedPosters = { ...loadedPosters, [key]: true };
  }

  function markPosterFailed(key: string): void {
    failedPosters = { ...failedPosters, [key]: true };
  }

  function selectEntry(entry: LibraryEntry): void {
    selectedEntry = entry;
  }
</script>

<section class="media-grid" aria-label="Library collection">
  {#each entries as entry (entry.key)}
    <article class:anime={entry.category === "anime"} class:shows={entry.category === "shows"}>
      <button
        type="button"
        class="entry-select"
        on:click={() => {
          selectEntry(entry);
        }}
      >
        <div class:poster-loaded={loadedPosters[entry.key]} class="cover">
          {#if entry.poster_url && !failedPosters[entry.key]}
            <img
              src={entry.poster_url}
              alt=""
              on:load={() => {
                markPosterLoaded(entry.key);
              }}
              on:error={() => {
                markPosterFailed(entry.key);
              }}
            />
          {/if}
          <span class="category">{categoryLabels[entry.category]}</span>
          <span class="cover-title" aria-hidden="true">
            {#each coverWords(entry.title) as word, index (index)}
              <span>{word}</span>
            {/each}
          </span>
          <span class="file-count"
            >{entry.file_count} {entry.file_count === 1 ? "file" : "files"}</span
          >
        </div>
        <span class="tile-details">
          <span class="tile-title" title={entry.title}>{entry.title}</span>
          <code title={entry.relative_path}>{entry.relative_path}</code>
        </span>
      </button>
    </article>
  {:else}
    <p class="empty">No generated entries match the current view.</p>
  {/each}
</section>

{#if selectedEntry}
  <LibraryEntryDialog
    entry={selectedEntry}
    currentOverride={classificationOverride(selectedEntry)}
    {disabled}
    pending={
      removingEntryKey === selectedEntry.key || pendingClassificationKey === selectedEntry.key
    }
    refreshing={refreshingMetadataKey === selectedEntry.key}
    onClose={() => {
      selectedEntry = null;
    }}
    {onMove}
    {onReset}
    {onRemove}
    {onRefresh}
  />
{/if}

<style>
  .media-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(178px, 1fr));
    gap: 16px;
  }

  article {
    min-width: 0;
  }

  .entry-select {
    display: grid;
    width: 100%;
    min-width: 0;
    gap: 10px;
    border: 0;
    padding: 0;
    background: transparent;
    color: inherit;
    cursor: pointer;
    text-align: left;
  }

  .entry-select:focus-visible .cover {
    outline: 2px solid #65b493;
    outline-offset: 3px;
  }

  .cover {
    position: relative;
    display: flex;
    min-height: 238px;
    aspect-ratio: 2 / 3;
    flex-direction: column;
    justify-content: space-between;
    overflow: hidden;
    border: 1px solid #62663a;
    border-radius: 6px;
    padding: 12px;
    background: #3d4024;
    color: #ffffe5;
  }

  .cover img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  article.shows .cover {
    border-color: #315052;
    background: #1f3f42;
    color: #ecfffb;
  }

  article.anime .cover {
    border-color: #58658f;
    background: #30384f;
    color: #f1f4ff;
  }

  .category,
  .file-count {
    position: relative;
    z-index: 1;
    align-self: flex-start;
    border: 1px solid currentColor;
    border-radius: 4px;
    padding: 3px 6px;
    background: #151815;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0;
    text-transform: uppercase;
  }

  .file-count {
    align-self: flex-end;
  }

  .cover-title {
    position: relative;
    z-index: 1;
    display: grid;
    gap: 1px;
    font-size: 24px;
    font-weight: 850;
    line-height: 0.96;
    overflow-wrap: anywhere;
    text-transform: uppercase;
  }

  .poster-loaded .cover-title {
    display: none;
  }

  .tile-details {
    display: grid;
    gap: 10px;
    padding: 0 2px;
  }

  .tile-title {
    display: -webkit-box;
    overflow: hidden;
    color: #f8f5ed;
    font-size: 14px;
    font-weight: 750;
    line-clamp: 2;
    line-height: 1.25;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
  }

  .tile-details code {
    display: block;
    overflow: hidden;
    margin-top: 4px;
    color: #aab9af;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
    font-size: 10px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .empty {
    grid-column: 1 / -1;
    margin: 0;
    padding: 42px 0;
    color: #aab9af;
    text-align: center;
  }

  @media (max-width: 560px) {
    .media-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }

    .cover {
      min-height: 210px;
    }

    .cover-title {
      font-size: 20px;
    }
  }
</style>
