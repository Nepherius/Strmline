<script lang="ts">
  import {
    categoryLabels,
    type LibraryCategory,
    type LibraryEntry,
  } from "$lib/domain/library/summary";
  import type { ClassificationOverride } from "$lib/api/library";

  export let entry: LibraryEntry;
  export let currentOverride: ClassificationOverride | null;
  export let pending = false;
  export let onClose: () => void;
  export let onMove: (entry: LibraryEntry, targetCategory: LibraryCategory) => Promise<void>;

  const categories: LibraryCategory[] = ["movies", "shows", "anime"];
  let targetCategory: LibraryCategory = "anime";

  $: targetCategory = defaultCategory(entry, currentOverride, targetCategory);
  $: submitLabel = targetCategory === currentOverride?.source_category ? "Restore" : "Move";

  function defaultCategory(
    nextEntry: LibraryEntry,
    override: ClassificationOverride | null,
    currentTarget: LibraryCategory,
  ): LibraryCategory {
    if (override && currentTarget === nextEntry.category) return override.source_category;
    if (currentTarget !== nextEntry.category) return currentTarget;
    if (nextEntry.category === "movies") return "anime";
    if (nextEntry.category === "shows") return "anime";
    return nextEntry.relative_path.includes("/Season ") ? "shows" : "movies";
  }
</script>

<div class="dialog-backdrop">
  <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="move-title" tabindex="-1">
    <div class="dialog-header">
      <h2 id="move-title">Move entry</h2>
      <button
        type="button"
        class="icon-button"
        aria-label="Close"
        disabled={pending}
        on:click={onClose}
      >
        x
      </button>
    </div>

    <div class="entry-summary">
      <strong>{entry.title}</strong>
      <code>{entry.relative_path}</code>
    </div>

    <label>
      Category
      <select bind:value={targetCategory} disabled={pending}>
        {#each categories as option (option)}
          <option value={option}>{categoryLabels[option]}</option>
        {/each}
      </select>
    </label>

    <div class="actions">
      <button type="button" class="secondary" disabled={pending} on:click={onClose}>Cancel</button>
      <button
        type="button"
        disabled={pending || targetCategory === entry.category}
        on:click={() => {
          void onMove(entry, targetCategory);
        }}
      >
        {pending ? "Moving" : submitLabel}
      </button>
    </div>
  </div>
</div>

<style>
  .dialog-backdrop {
    position: fixed;
    inset: 0;
    z-index: 20;
    display: grid;
    place-items: center;
    padding: 18px;
    background: rgb(11 20 16 / 42%);
  }

  .dialog {
    display: grid;
    width: min(440px, 100%);
    gap: 16px;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 18px;
    background: var(--surface);
    box-shadow: 0 18px 50px rgb(0 0 0 / 42%);
  }

  .dialog-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  h2 {
    margin: 0;
    letter-spacing: 0;
    font-size: 18px;
  }

  .icon-button {
    width: 32px;
    height: 32px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--surface-raised);
    color: var(--text-soft);
    cursor: pointer;
    font-size: 20px;
    line-height: 1;
  }

  .entry-summary {
    display: grid;
    gap: 6px;
  }

  code {
    overflow-wrap: anywhere;
    color: var(--text-muted);
    font-size: 12px;
  }

  label {
    display: grid;
    gap: 6px;
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 800;
    text-transform: uppercase;
  }

  select {
    height: 38px;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0 10px;
    background: var(--surface-raised);
    color: var(--text-soft);
    font-size: 14px;
    text-transform: none;
  }

  .actions {
    display: flex;
    justify-content: end;
    gap: 8px;
  }

  .actions button {
    height: 36px;
    border: 1px solid var(--accent-strong);
    border-radius: 6px;
    padding: 0 14px;
    background: var(--accent);
    color: var(--text);
    cursor: pointer;
    font-weight: 800;
  }

  .actions button.secondary {
    border-color: var(--border);
    background: var(--surface-raised);
    color: var(--text-soft);
  }

  button:disabled,
  select:disabled {
    cursor: wait;
    opacity: 0.6;
  }
</style>
