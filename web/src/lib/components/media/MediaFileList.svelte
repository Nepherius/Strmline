<script lang="ts">
  import type { MediaFileManifest } from "$lib/domain/fileManifest";
  import { episodeLabel, formatFileSize } from "$lib/domain/fileManifest";

  export let manifest: MediaFileManifest;
</script>

{#if manifest.available}
  <div class="manifest-summary">
    <span>
      {manifest.total_files}
      {manifest.total_files === 1 ? "file" : "files"}
      {#if manifest.displayed_files < manifest.total_files}
        · {manifest.displayed_files} episodes
      {/if}
    </span>
    {#if manifest.source_count > 1}
      <span>{manifest.source_count} sources</span>
    {/if}
  </div>

  <ul class="file-list">
    {#each manifest.files as file (file.key)}
      <li>
        <div class="file-heading">
          {#if episodeLabel(file)}
            <span class="episode-label">{episodeLabel(file)}</span>
          {/if}
          <span class="file-name">{file.name}</span>
          {#if file.version_count > 1}
            <span
              class="versions-icon"
              title="Multiple versions of the episode exist"
              aria-label="Multiple versions of the episode exist"
            >
              <svg aria-hidden="true" viewBox="0 0 24 24">
                <rect x="4" y="7" width="12" height="12" rx="2"></rect>
                <rect x="8" y="3" width="12" height="12" rx="2"></rect>
              </svg>
            </span>
          {/if}
        </div>
        <div class="file-meta">
          {#if file.path !== file.name}
            <span title={file.path}>{file.path}</span>
          {/if}
          {#if formatFileSize(file.size)}
            <span>{formatFileSize(file.size)}</span>
          {/if}
        </div>
      </li>
    {/each}
  </ul>
{:else}
  <p class:lookup-error={!manifest.ok} class="unavailable">{manifest.message}</p>
{/if}

<style>
  .manifest-summary {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    color: var(--text-muted);
    font-size: 12px;
  }

  .file-list {
    display: grid;
    max-height: min(44vh, 460px);
    gap: 0;
    overflow: auto;
    border: 1px solid var(--border);
    border-radius: 6px;
    margin: 10px 0 0;
    padding: 0;
    background: var(--surface-subtle);
    list-style: none;
  }

  li {
    min-width: 0;
    border-bottom: 1px solid var(--border);
    padding: 10px 12px;
  }

  li:last-child {
    border-bottom: 0;
  }

  .file-heading {
    display: flex;
    min-width: 0;
    align-items: center;
    gap: 8px;
  }

  .episode-label {
    flex: 0 0 auto;
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 2px 7px;
    color: var(--text-soft);
    font-size: 10px;
    font-weight: 800;
  }

  .file-name {
    min-width: 0;
    overflow-wrap: anywhere;
    color: var(--text);
    font-size: 13px;
    font-weight: 700;
  }

  .versions-icon {
    display: inline-grid;
    width: 22px;
    height: 22px;
    flex: 0 0 auto;
    place-items: center;
    color: var(--accent-strong);
    cursor: help;
  }

  .versions-icon svg {
    width: 18px;
    height: 18px;
    fill: var(--surface);
    stroke: currentcolor;
    stroke-width: 1.7;
  }

  .file-meta {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    margin-top: 4px;
    color: var(--text-muted);
    font-size: 11px;
  }

  .file-meta span:first-child {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .file-meta span:last-child {
    flex: 0 0 auto;
  }

  .unavailable {
    border: 1px solid var(--border);
    border-radius: 6px;
    margin: 0;
    padding: 14px;
    background: var(--surface-subtle);
    color: var(--text-muted);
    font-size: 13px;
  }

  .lookup-error {
    border-color: var(--danger-border);
    color: var(--danger-text);
  }
</style>
