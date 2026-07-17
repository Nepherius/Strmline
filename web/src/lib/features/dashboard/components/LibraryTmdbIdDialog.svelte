<script lang="ts">
  import Notice from "$lib/components/ui/Notice.svelte";
  import type { LibraryEntry } from "$lib/domain/library/summary";

  export let entry: LibraryEntry;
  export let pending = false;
  export let onClose: () => void;
  export let onSave: (entry: LibraryEntry, tmdbId: number) => Promise<void>;

  let tmdbId = entry.tmdb_id === null || entry.tmdb_id === undefined ? "" : String(entry.tmdb_id);
  let saveError = "";
  $: parsedTmdbId = Number(tmdbId);
  $: validTmdbId = /^\d+$/.test(tmdbId) && Number.isSafeInteger(parsedTmdbId) && parsedTmdbId > 0;

  async function saveTmdbId(): Promise<void> {
    if (!validTmdbId) return;
    saveError = "";
    try {
      await onSave(entry, parsedTmdbId);
    } catch (caughtError) {
      saveError = caughtError instanceof Error ? caughtError.message : "TMDB ID update failed.";
    }
  }
</script>

<svelte:window
  on:keydown={(event) => {
    if (event.key === "Escape" && !pending) onClose();
  }}
/>

<div class="dialog-backdrop" role="presentation">
  <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="tmdb-title" tabindex="-1">
    <form
      on:submit|preventDefault={() => {
        void saveTmdbId();
      }}
    >
      <div class="dialog-header">
        <div>
          <span>Metadata identity</span>
          <h2 id="tmdb-title">{entry.tmdb_id ? "Change TMDB ID" : "Set TMDB ID"}</h2>
        </div>
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

      <p>
        Enter the numeric ID from the TMDB URL for <strong>{entry.title}</strong>. Strmline will
        save it as the authoritative ID for future syncs and immediately refresh the title, year,
        and poster from that exact ID.
      </p>

      <label>
        TMDB ID
        <input
          bind:value={tmdbId}
          type="number"
          inputmode="numeric"
          min="1"
          step="1"
          placeholder="For example, 550"
          disabled={pending}
        />
      </label>

      {#if saveError}
        <Notice variant="error" resetKey={saveError}>{saveError}</Notice>
      {/if}

      <div class="actions">
        <button type="button" class="secondary" disabled={pending} on:click={onClose}>Cancel</button
        >
        <button type="submit" disabled={pending || !validTmdbId}>
          {pending ? "Saving and refreshing" : "Save TMDB ID"}
        </button>
      </div>
    </form>
  </div>
</div>

<style>
  .dialog-backdrop {
    position: fixed;
    inset: 0;
    z-index: 40;
    display: grid;
    place-items: center;
    padding: 18px;
    background: rgb(4 9 6 / 76%);
  }

  .dialog {
    width: min(460px, 100%);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 18px;
    background: var(--surface);
    color: var(--text);
    box-shadow: 0 18px 50px rgb(0 0 0 / 42%);
  }

  form {
    display: grid;
    gap: 16px;
  }

  .dialog-header {
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: 12px;
  }

  .dialog-header span,
  label {
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 800;
    text-transform: uppercase;
  }

  h2 {
    margin: 3px 0 0;
    font-size: 19px;
  }

  p {
    margin: 0;
    color: var(--text-soft);
    font-size: 14px;
    line-height: 1.5;
  }

  label {
    display: grid;
    gap: 6px;
  }

  input {
    box-sizing: border-box;
    width: 100%;
    height: 40px;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0 10px;
    background: var(--surface-raised);
    color: var(--text);
    font-size: 15px;
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
  input:disabled {
    cursor: wait;
    opacity: 0.6;
  }
</style>
