<script lang="ts">
  import type { StreamSearchResult } from "$lib/domain/search/types";
  import {
    getQualityBadgeClass,
    formatCodecAndHdr,
    formatAudio,
    formatLanguage,
  } from "$lib/domain/search/presentation";

  export let stream: StreamSearchResult;
  export let pending = false;
  export let onAdd: (stream: StreamSearchResult) => Promise<void>;
  export let onRemove: (stream: StreamSearchResult) => Promise<void>;
  export let onInspect: (stream: StreamSearchResult) => Promise<void>;

  $: hasAction = stream.selected || stream.addable;
  $: canInspect = stream.has_info_hash || stream.selected;

  function handleAction() {
    if (pending || !hasAction) return;
    if (stream.selected) {
      void onRemove(stream);
      return;
    }
    void onAdd(stream);
  }
</script>

<div class="stream-item">
  <div class="stream-main">
    <div class="badges-row">
      {#if stream.provider_label}
        <span class="badge badge-provider">{stream.provider_label}</span>
      {/if}

      {#if stream.selected}
        <span class="badge badge-selected">Saved</span>
      {/if}

      {#if stream.parsed.quality}
        <span class="badge {getQualityBadgeClass(stream.parsed.quality)}">
          {stream.parsed.quality}
        </span>
      {/if}

      {#if stream.parsed.size_label}
        <span class="badge badge-gray">{stream.parsed.size_label}</span>
      {/if}

      {#if stream.seeders !== null}
        <span class="badge badge-gray">Seeders {stream.seeders}</span>
      {/if}
    </div>
    <h4 class="stream-title">{stream.title}</h4>
    <div class="stream-meta">
      <span>{formatCodecAndHdr(stream.parsed)}</span>
      <span>&middot;</span>
      <span>{formatAudio(stream.parsed)}</span>
      <span>&middot;</span>
      <span>{formatLanguage(stream.parsed)}</span>
    </div>
  </div>
  <div class="stream-actions">
    <span
      class="files-control"
      title={canInspect
        ? "View included files"
        : "No torrent hash was supplied. Use a current AIOStreams version and its full per-user manifest URL."}
    >
      <button
        type="button"
        class="files-action"
        disabled={pending || !canInspect}
        on:click={() => void onInspect(stream)}
      >
        Files
      </button>
    </span>
    {#if hasAction}
      <button
        type="button"
        class:remove={stream.selected}
        disabled={pending}
        on:click={handleAction}
      >
        {#if pending}
          Working
        {:else if stream.selected}
          Remove
        {:else}
          Add
        {/if}
      </button>
    {/if}
  </div>
</div>

<style>
  .stream-item {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .stream-main {
    flex: 1;
    min-width: 0;
  }

  .stream-actions {
    display: flex;
    gap: 8px;
    margin-left: 16px;
    flex: 0 0 auto;
  }

  .stream-actions button {
    min-width: 104px;
    height: 34px;
    border: 1px solid var(--accent-strong);
    border-radius: 6px;
    background: var(--accent);
    color: var(--text);
    cursor: pointer;
    font-weight: 700;
  }

  .stream-actions button.remove {
    border-color: var(--danger-border);
    background: var(--danger-surface);
    color: var(--danger-text);
  }

  .stream-actions button.files-action {
    min-width: 72px;
    border-color: var(--border);
    background: var(--surface-raised);
    color: var(--text-soft);
  }

  .files-control {
    display: flex;
  }

  .stream-actions button:disabled {
    cursor: not-allowed;
    opacity: 0.62;
  }

  .badges-row {
    display: flex;
    gap: 8px;
    margin-bottom: 8px;
    flex-wrap: wrap;
  }

  .badge {
    font-size: 11px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 999px;
  }

  .badge-provider {
    background: var(--surface-raised);
    color: var(--text-soft);
    border: 1px solid var(--border);
  }

  .badge-selected {
    background: var(--success-surface);
    color: var(--success-text);
    border: 1px solid var(--success-border);
  }

  .badge-purple {
    background: #30384f;
    color: #d5d9ff;
    border: 1px solid #58658f;
  }

  .badge-blue {
    background: #1e3543;
    color: #b6e3f5;
    border: 1px solid #41748d;
  }

  .badge-green {
    background: var(--success-surface);
    color: var(--success-text);
    border: 1px solid var(--success-border);
  }

  .badge-yellow {
    background: var(--warning-surface);
    color: var(--warning-text);
    border: 1px solid var(--warning-border);
  }

  .badge-red {
    background: var(--danger-surface);
    color: var(--danger-text);
    border: 1px solid var(--danger-border);
  }

  .badge-gray {
    background: var(--surface-subtle);
    color: var(--text-muted);
    border: 1px solid var(--border);
  }

  .stream-title {
    margin: 0 0 6px;
    font-size: 14px;
    font-weight: 700;
    color: var(--text);
    word-break: break-all;
  }

  .stream-meta {
    display: flex;
    gap: 8px;
    font-size: 12px;
    color: var(--text-muted);
    flex-wrap: wrap;
  }

  @media (max-width: 760px) {
    .stream-item {
      align-items: stretch;
      flex-direction: column;
    }

    .stream-actions {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      margin-left: 0;
      margin-top: 12px;
    }

    .stream-actions button {
      width: 100%;
    }
  }
</style>
