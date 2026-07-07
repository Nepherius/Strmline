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

  $: hasAction = stream.selected || stream.addable;

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
  {#if hasAction}
    <div class="stream-actions">
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
    </div>
  {/if}
</div>

<style>
  .stream-item {
    background: #ffffff;
    border: 1px solid #d7ded9;
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
    margin-left: 16px;
    flex: 0 0 auto;
  }

  .stream-actions button {
    min-width: 104px;
    height: 34px;
    border: 1px solid #1c4333;
    border-radius: 6px;
    background: #1f5b42;
    color: #ffffff;
    cursor: pointer;
    font-weight: 700;
  }

  .stream-actions button.remove {
    border-color: #a23a35;
    background: #fff5f4;
    color: #8e251f;
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
    background: #eef3f0;
    color: #1f5b42;
    border: 1px solid #bdc8c2;
  }

  .badge-selected {
    background: #e8f7ef;
    color: #1f5b42;
    border: 1px solid #9bc9aa;
  }

  .badge-purple {
    background: #f3f0ff;
    color: #6b46c1;
    border: 1px solid #d6bcfa;
  }

  .badge-blue {
    background: #ebf8ff;
    color: #2b6cb0;
    border: 1px solid #bee3f8;
  }

  .badge-green {
    background: #f0fff4;
    color: #2f855a;
    border: 1px solid #c6f6d5;
  }

  .badge-yellow {
    background: #fffaf0;
    color: #b7791f;
    border: 1px solid #feebc8;
  }

  .badge-red {
    background: #fff5f5;
    color: #c53030;
    border: 1px solid #fed7d7;
  }

  .badge-gray {
    background: #f7fafc;
    color: #4a5568;
    border: 1px solid #e2e8f0;
  }

  .stream-title {
    margin: 0 0 6px;
    font-size: 14px;
    font-weight: 700;
    color: #15201b;
    word-break: break-all;
  }

  .stream-meta {
    display: flex;
    gap: 8px;
    font-size: 12px;
    color: #5b6a61;
    flex-wrap: wrap;
  }

  @media (max-width: 760px) {
    .stream-item {
      align-items: stretch;
      flex-direction: column;
    }

    .stream-actions {
      margin-left: 0;
      margin-top: 12px;
    }

    .stream-actions button {
      width: 100%;
    }
  }
</style>
