<script lang="ts">
  import type { ClassificationOverride } from "$lib/api/library";
  import {
    categoryLabels,
    type LibraryCategory,
    type LibraryEntry,
  } from "$lib/domain/library/summary";

  import LibraryEntryActions from "./LibraryEntryActions.svelte";

  export let entry: LibraryEntry;
  export let currentOverride: ClassificationOverride | null;
  export let disabled = false;
  export let pending = false;
  export let refreshing = false;
  export let onClose: () => void;
  export let onMove: (entry: LibraryEntry, targetCategory: LibraryCategory) => Promise<void>;
  export let onReset: (entry: LibraryEntry) => Promise<void>;
  export let onRemove: (entry: LibraryEntry) => Promise<void>;
  export let onRefresh: (entry: LibraryEntry) => Promise<void>;
  export let onRemoveWatchlist: (entry: LibraryEntry) => Promise<void>;
  export let onSearchWatchlist: (entry: LibraryEntry) => void;

  async function moveEntry(
    nextEntry: LibraryEntry,
    targetCategory: LibraryCategory,
  ): Promise<void> {
    await onMove(nextEntry, targetCategory);
    onClose();
  }

  async function resetEntry(nextEntry: LibraryEntry): Promise<void> {
    await onReset(nextEntry);
    onClose();
  }

  async function refreshEntry(nextEntry: LibraryEntry): Promise<void> {
    await onRefresh(nextEntry);
    onClose();
  }

  async function removeEntry(nextEntry: LibraryEntry): Promise<void> {
    await onRemove(nextEntry);
    onClose();
  }

  async function removeWatchlistEntry(nextEntry: LibraryEntry): Promise<void> {
    await onRemoveWatchlist(nextEntry);
    onClose();
  }

  function searchWatchlistEntry(nextEntry: LibraryEntry): void {
    onSearchWatchlist(nextEntry);
    onClose();
  }
</script>

<svelte:window
  on:keydown={(event) => {
    if (event.key === "Escape" && !pending && !refreshing) onClose();
  }}
/>

<div
  class="dialog-backdrop"
  role="presentation"
  on:click|self={() => {
    if (!pending && !refreshing) onClose();
  }}
>
  <dialog open class="dialog" aria-labelledby="entry-title">
    <header>
      <div>
        <span>{categoryLabels[entry.category]}</span>
        <h2 id="entry-title">{entry.title}</h2>
      </div>
      <button
        type="button"
        aria-label="Close entry details"
        title="Close"
        disabled={pending || refreshing}
        on:click={onClose}>x</button
      >
    </header>

    <div class="content">
      <div class="poster" class:empty={!entry.poster_url}>
        {#if entry.poster_url}
          <img src={entry.poster_url} alt="" />
        {:else}
          <span>{categoryLabels[entry.category]}</span>
        {/if}
      </div>
      <dl>
        {#if entry.category === "watchlist"}
          {#if entry.year}
            <div>
              <dt>Year</dt>
              <dd>{entry.year}</dd>
            </div>
          {/if}
          <div>
            <dt>Status</dt>
            <dd>Saved for later</dd>
          </div>
          {#if entry.overview}
            <div>
              <dt>Overview</dt>
              <dd class="overview">{entry.overview}</dd>
            </div>
          {/if}
        {:else}
          <div>
            <dt>Files</dt>
            <dd>{entry.file_count}</dd>
          </div>
          <div>
            <dt>Location</dt>
            <dd><code>{entry.relative_path}</code></dd>
          </div>
        {/if}
      </dl>
    </div>

    <footer>
      {#if entry.category === "watchlist"}
        <div class="watchlist-actions">
          <button
            type="button"
            class="danger-action"
            disabled={disabled || pending}
            on:click={() => void removeWatchlistEntry(entry)}
          >
            {pending ? "Removing" : "Remove from watchlist"}
          </button>
          <button
            type="button"
            class="search-action"
            disabled={disabled || pending}
            on:click={() => {
              searchWatchlistEntry(entry);
            }}>Search</button
          >
        </div>
      {:else}
        <LibraryEntryActions
          {entry}
          {currentOverride}
          {disabled}
          {pending}
          {refreshing}
          onMove={moveEntry}
          onReset={resetEntry}
          onRemove={removeEntry}
          onRefresh={refreshEntry}
        />
      {/if}
    </footer>
  </dialog>
</div>

<style>
  .dialog-backdrop {
    position: fixed;
    inset: 0;
    z-index: 30;
    display: grid;
    place-items: center;
    padding: 18px;
    background: rgb(4 9 6 / 68%);
  }

  .dialog {
    position: relative;
    inset: auto;
    display: grid;
    width: min(620px, 100%);
    gap: 18px;
    border: 1px solid #3b4840;
    border-radius: 6px;
    margin: 0;
    padding: 18px;
    background: #202620;
    color: #f8f5ed;
    box-shadow: 0 18px 50px rgb(0 0 0 / 36%);
  }

  header,
  .content,
  footer {
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: 16px;
  }

  header > div {
    min-width: 0;
  }

  header span,
  dt {
    color: #aab9af;
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
  }

  h2 {
    margin: 4px 0 0;
    overflow-wrap: anywhere;
    font-size: 20px;
  }

  header button {
    display: grid;
    width: 32px;
    height: 32px;
    flex: 0 0 auto;
    place-items: center;
    border: 1px solid #3b4840;
    border-radius: 6px;
    padding: 0;
    background: #151815;
    color: #f8f5ed;
    cursor: pointer;
    font-size: 18px;
  }

  .content {
    align-items: stretch;
  }

  .poster {
    width: 116px;
    min-width: 116px;
    aspect-ratio: 2 / 3;
    overflow: hidden;
    border: 1px solid #3b4840;
    border-radius: 6px;
    background: #151815;
  }

  .poster img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .poster.empty {
    display: grid;
    place-items: center;
    padding: 12px;
    color: #aab9af;
    font-size: 11px;
    font-weight: 800;
    text-align: center;
    text-transform: uppercase;
  }

  dl {
    display: grid;
    width: 100%;
    gap: 12px;
    margin: 0;
  }

  dl div {
    display: grid;
    gap: 4px;
  }

  dd {
    margin: 0;
    color: #f8f5ed;
  }

  .overview {
    color: #dbe6dd;
    font-size: 13px;
    line-height: 1.45;
  }

  code {
    overflow-wrap: anywhere;
    color: #dbe6dd;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
    font-size: 12px;
  }

  footer {
    justify-content: end;
    border-top: 1px solid #3b4840;
    padding-top: 14px;
  }

  .watchlist-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: end;
    gap: 8px;
  }

  .watchlist-actions button {
    height: 36px;
    border: 1px solid #3e9c7a;
    border-radius: 6px;
    padding: 0 14px;
    background: #26795e;
    color: #fff;
    cursor: pointer;
    font-weight: 800;
  }

  .watchlist-actions .danger-action {
    border-color: #a35a51;
    background: #32201f;
    color: #ffd7d2;
  }

  button:disabled {
    cursor: wait;
    opacity: 0.6;
  }

  @media (max-width: 480px) {
    .content {
      align-items: start;
      flex-direction: column;
    }

    .poster {
      width: 90px;
      min-width: 90px;
    }
  }
</style>
