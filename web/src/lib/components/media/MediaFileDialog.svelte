<script lang="ts">
  import type { MediaFileManifest } from "$lib/domain/fileManifest";
  import MediaFileList from "./MediaFileList.svelte";

  export let title: string;
  export let loading: boolean;
  export let manifest: MediaFileManifest | null;
  export let onClose: () => void;
</script>

<svelte:window
  on:keydown={(event) => {
    if (event.key === "Escape") onClose();
  }}
/>

<div class="dialog-backdrop" role="presentation" on:click|self={onClose}>
  <dialog open class="dialog" aria-labelledby="file-dialog-title">
    <header>
      <div>
        <span>Included files</span>
        <h2 id="file-dialog-title">{title}</h2>
      </div>
      <button type="button" aria-label="Close included files" title="Close" on:click={onClose}
        >×</button
      >
    </header>

    {#if loading}
      <div class="loading-state">
        <span class="spinner" aria-hidden="true"></span>
        <span>Loading included files…</span>
      </div>
    {:else if manifest}
      <MediaFileList {manifest} />
    {/if}
  </dialog>
</div>

<style>
  .dialog-backdrop {
    position: fixed;
    inset: 0;
    z-index: 45;
    display: grid;
    place-items: center;
    padding: 18px;
    background: rgb(4 9 6 / 72%);
  }

  .dialog {
    position: relative;
    inset: auto;
    display: grid;
    width: min(760px, 100%);
    max-height: calc(100vh - 36px);
    gap: 16px;
    overflow: hidden;
    border: 1px solid var(--border);
    border-radius: 8px;
    margin: 0;
    padding: 18px;
    background: var(--surface);
    color: var(--text);
    box-shadow: 0 18px 50px rgb(0 0 0 / 42%);
  }

  header {
    display: flex;
    min-width: 0;
    align-items: start;
    justify-content: space-between;
    gap: 16px;
  }

  header > div {
    min-width: 0;
  }

  header span {
    color: var(--text-muted);
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
  }

  h2 {
    margin: 4px 0 0;
    overflow-wrap: anywhere;
    font-size: 18px;
  }

  header button {
    display: grid;
    width: 32px;
    height: 32px;
    flex: 0 0 auto;
    place-items: center;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0;
    background: var(--surface-raised);
    color: var(--text);
    cursor: pointer;
    font-size: 20px;
  }

  .loading-state {
    display: flex;
    min-height: 120px;
    align-items: center;
    justify-content: center;
    gap: 10px;
    color: var(--text-muted);
  }

  .spinner {
    width: 18px;
    height: 18px;
    border: 2px solid var(--border);
    border-top-color: var(--accent-strong);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
