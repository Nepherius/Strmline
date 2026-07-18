<script lang="ts">
  import { onMount } from "svelte";

  import type { ClassificationOverride } from "$lib/api/library";
  import {
    categoryLabels,
    type LibraryCategory,
    type LibraryEntry,
  } from "$lib/domain/library/summary";

  import LibraryEntryDialog from "./LibraryEntryDialog.svelte";
  import LibraryHealthChip from "./LibraryHealthChip.svelte";

  export let entries: LibraryEntry[];
  export let overrides: ClassificationOverride[];
  export let disabled = false;
  export let checkingHealth = false;
  export let pendingClassificationKey = "";
  export let removingEntryKey = "";
  export let refreshingMetadataKey = "";
  export let updatingTmdbKey = "";
  export let onMove: (entry: LibraryEntry, targetCategory: LibraryCategory) => Promise<void>;
  export let onReset: (entry: LibraryEntry) => Promise<void>;
  export let onRemove: (entry: LibraryEntry) => Promise<void>;
  export let onRefresh: (entry: LibraryEntry) => Promise<void>;
  export let onUpdateTmdb: (entry: LibraryEntry, tmdbId: number) => Promise<void>;
  export let onRemoveWatchlist: (entry: LibraryEntry) => Promise<void>;
  export let onSearchWatchlist: (entry: LibraryEntry) => void;
  export let hasMore = false;
  export let loadingMore = false;
  export let onNeedMore: () => Promise<void>;

  let loadedPosters: Record<string, boolean> = {};
  let failedPosters: Record<string, boolean> = {};
  let posterSources: Record<string, string> = {};
  let selectedEntry: LibraryEntry | null = null;
  // Svelte 4 does not provide the reactive collection wrappers suggested by the lint rule.
  // eslint-disable-next-line svelte/prefer-svelte-reactivity
  const posterTargets = new Map<HTMLElement, LibraryEntry>();
  const posterQueue: LibraryEntry[] = [];
  // eslint-disable-next-line svelte/prefer-svelte-reactivity
  const queuedPosterKeys = new Set<string>();
  // eslint-disable-next-line svelte/prefer-svelte-reactivity
  const activePosterKeys = new Set<string>();
  const maxConcurrentPosterLoads = 4;
  let activePosterLoads = 0;
  let posterObserver: IntersectionObserver | undefined;
  let loadMoreObserver: IntersectionObserver | undefined;
  let loadMoreTarget: HTMLElement | undefined;

  onMount(() => {
    posterObserver = new IntersectionObserver(
      (observedEntries) => {
        for (const observedEntry of observedEntries) {
          if (!observedEntry.isIntersecting) {
            continue;
          }
          const entry = posterTargets.get(observedEntry.target as HTMLElement);
          if (entry) {
            queuePoster(entry);
          }
          posterObserver?.unobserve(observedEntry.target);
        }
      },
      { rootMargin: "320px 0px" },
    );
    for (const target of posterTargets.keys()) {
      posterObserver.observe(target);
    }
    loadMoreObserver = new IntersectionObserver(
      (observedEntries) => {
        if (observedEntries.some((entry) => entry.isIntersecting) && hasMore && !loadingMore) {
          void onNeedMore();
        }
      },
      { rootMargin: "800px 0px" },
    );
    if (loadMoreTarget) loadMoreObserver.observe(loadMoreTarget);
    return () => {
      posterObserver?.disconnect();
      loadMoreObserver?.disconnect();
    };
  });

  function classificationOverride(entry: LibraryEntry): ClassificationOverride | null {
    if (entry.category === "watchlist") return null;
    return (
      overrides.find((override) => override.target_prefix === entry.relative_path) ??
      overrides.find((override) => override.source_prefix === entry.relative_path) ??
      null
    );
  }

  function coverWords(title: string): string[] {
    return title.split(/\s+/).filter(Boolean).slice(0, 4);
  }

  function observePoster(node: HTMLElement, entry: LibraryEntry): { destroy: () => void } {
    posterTargets.set(node, entry);
    posterObserver?.observe(node);
    return {
      destroy: () => {
        posterTargets.delete(node);
        posterObserver?.unobserve(node);
        posterLoadFinished(entry.key);
      },
    };
  }

  function observeLoadMore(node: HTMLElement): { destroy: () => void } {
    loadMoreTarget = node;
    loadMoreObserver?.observe(node);
    return {
      destroy: () => {
        loadMoreObserver?.unobserve(node);
        if (loadMoreTarget === node) loadMoreTarget = undefined;
      },
    };
  }

  function queuePoster(entry: LibraryEntry): void {
    if (
      !entry.poster_url ||
      posterSources[entry.key] ||
      failedPosters[entry.key] ||
      queuedPosterKeys.has(entry.key)
    ) {
      return;
    }
    queuedPosterKeys.add(entry.key);
    posterQueue.push(entry);
    startQueuedPosterLoads();
  }

  function startQueuedPosterLoads(): void {
    while (activePosterLoads < maxConcurrentPosterLoads && posterQueue.length > 0) {
      const entry = posterQueue.shift();
      if (!entry?.poster_url) {
        continue;
      }
      queuedPosterKeys.delete(entry.key);
      activePosterLoads += 1;
      activePosterKeys.add(entry.key);
      posterSources = { ...posterSources, [entry.key]: entry.poster_url };
    }
  }

  function markPosterLoaded(key: string): void {
    loadedPosters = { ...loadedPosters, [key]: true };
    posterLoadFinished(key);
  }

  function markPosterFailed(key: string): void {
    failedPosters = { ...failedPosters, [key]: true };
    posterLoadFinished(key);
  }

  function posterLoadFinished(key: string): void {
    if (!activePosterKeys.delete(key)) {
      return;
    }
    activePosterLoads = activePosterKeys.size;
    startQueuedPosterLoads();
  }

  function selectEntry(entry: LibraryEntry): void {
    selectedEntry = entry;
  }
</script>

<section class="media-grid" aria-label="Library collection">
  {#each entries as entry (entry.key)}
    <article
      class:anime={entry.category === "anime"}
      class:shows={entry.category === "shows"}
      class:watchlist={entry.category === "watchlist"}
    >
      <button
        type="button"
        class="entry-select"
        on:click={() => {
          selectEntry(entry);
        }}
      >
        <div use:observePoster={entry} class:poster-loaded={loadedPosters[entry.key]} class="cover">
          {#if posterSources[entry.key] && !failedPosters[entry.key]}
            <img
              src={posterSources[entry.key]}
              alt=""
              decoding="async"
              on:load={() => {
                markPosterLoaded(entry.key);
              }}
              on:error={() => {
                markPosterFailed(entry.key);
              }}
            />
          {/if}
          <span class="category">{categoryLabels[entry.category]}</span>
          {#if entry.category !== "watchlist"}
            <LibraryHealthChip health={entry.health} checking={checkingHealth} />
          {/if}
          <span class="cover-title" aria-hidden="true">
            {#each coverWords(entry.title) as word, index (index)}
              <span>{word}</span>
            {/each}
          </span>
          <span class="file-count">
            {entry.category === "watchlist"
              ? "Saved"
              : `${String(entry.file_count)} ${entry.file_count === 1 ? "file" : "files"}`}
          </span>
        </div>
        <span class="tile-details">
          <span class="tile-title" title={entry.title}>{entry.title}</span>
          <!-- {#if entry.category === "watchlist"}
            <code>{entry.year ?? "Series"} · Awaiting torrent</code>
          {:else}
            <code title={entry.relative_path}>{entry.relative_path}</code>
          {/if} -->
        </span>
      </button>
    </article>
  {:else}
    <p class="empty">No entries match the current view.</p>
  {/each}
</section>

{#if hasMore}
  <div class="load-more" use:observeLoadMore>
    <button type="button" disabled={loadingMore} on:click={onNeedMore}>
      {loadingMore ? "Loading more titles…" : "Load more titles"}
    </button>
  </div>
{/if}

{#if selectedEntry}
  <LibraryEntryDialog
    entry={selectedEntry}
    currentOverride={classificationOverride(selectedEntry)}
    {disabled}
    pending={removingEntryKey === selectedEntry.key ||
      pendingClassificationKey === selectedEntry.key}
    refreshing={refreshingMetadataKey === selectedEntry.key}
    updatingTmdb={updatingTmdbKey === selectedEntry.key}
    onClose={() => {
      selectedEntry = null;
    }}
    {onMove}
    {onReset}
    {onRemove}
    {onRefresh}
    {onUpdateTmdb}
    {onRemoveWatchlist}
    {onSearchWatchlist}
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
    content-visibility: auto;
    contain-intrinsic-size: auto 310px;
  }

  .load-more {
    display: grid;
    min-height: 72px;
    place-items: center;
  }

  .load-more button {
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 16px;
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
  }

  .load-more button:disabled {
    cursor: wait;
    opacity: 0.7;
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

  article.watchlist .cover {
    border-color: #8a7044;
    background: #463a25;
    color: #fff2ce;
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
