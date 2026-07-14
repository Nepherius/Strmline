<script lang="ts">
  import { type LibraryCategory, type LibraryEntry } from "$lib/domain/library/summary";
  import type { ClassificationOverride } from "$lib/api/library";
  import LibraryMoveDialog from "./LibraryMoveDialog.svelte";

  export let entry: LibraryEntry;
  export let currentOverride: ClassificationOverride | null;
  export let disabled = false;
  export let pending = false;
  export let refreshing = false;
  export let onMove: (entry: LibraryEntry, targetCategory: LibraryCategory) => Promise<void>;
  export let onReset: (entry: LibraryEntry) => Promise<void>;
  export let onRemove: (entry: LibraryEntry) => Promise<void>;
  export let onRefresh: (entry: LibraryEntry) => Promise<void>;

  let moveDialogOpen = false;
  $: restoreLabel = currentOverride ? `Restore category` : "";
  $: showRestore = currentOverride !== null && currentOverride.source_category !== entry.category;

  async function moveEntry(nextEntry: LibraryEntry, targetCategory: LibraryCategory) {
    await onMove(nextEntry, targetCategory);
    moveDialogOpen = false;
  }
</script>

<div class="entry-actions">
  <button
    type="button"
    class="icon-action"
    disabled={disabled || pending}
    title="Move category"
    aria-label="Move category"
    on:click={() => {
      moveDialogOpen = true;
    }}
  >
    <span aria-hidden="true">{pending ? "..." : "⇄"}</span>
  </button>
  {#if showRestore}
    <button
      type="button"
      class="icon-action secondary"
      disabled={disabled || pending}
      title={restoreLabel}
      aria-label={restoreLabel}
      on:click={() => {
        void onReset(entry);
      }}
    >
      <span aria-hidden="true">{pending ? "..." : "↺"}</span>
    </button>
  {/if}
  <button
    type="button"
    class="icon-action secondary"
    disabled={disabled || pending || refreshing}
    title="Refresh metadata and poster"
    aria-label="Refresh metadata and poster"
    on:click={() => {
      void onRefresh(entry);
    }}
  >
    <span aria-hidden="true">{refreshing ? "..." : "↻"}</span>
  </button>
  <button
    type="button"
    class="icon-action danger"
    disabled={disabled || pending || refreshing}
    title="Remove from Strmline and TorBox"
    aria-label="Remove from Strmline and TorBox"
    on:click={() => {
      void onRemove(entry);
    }}
  >
    <span aria-hidden="true">{pending ? "..." : "×"}</span>
  </button>
</div>

{#if moveDialogOpen}
  <LibraryMoveDialog
    {entry}
    {currentOverride}
    {pending}
    onClose={() => {
      moveDialogOpen = false;
    }}
    onMove={moveEntry}
  />
{/if}

<style>
  .entry-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .icon-action {
    display: inline-grid;
    place-items: center;
    width: 32px;
    height: 32px;
    border: 1px solid #bdc8c2;
    border-radius: 6px;
    padding: 0;
    background: #ffffff;
    color: #24352d;
    cursor: pointer;
    font-size: 18px;
    font-weight: 800;
    line-height: 1;
  }

  .icon-action.secondary {
    color: #1f5b42;
  }

  .icon-action.danger {
    border-color: #d7aca7;
    color: #8d2d23;
  }

  .icon-action:disabled {
    cursor: wait;
    opacity: 0.6;
  }
</style>
