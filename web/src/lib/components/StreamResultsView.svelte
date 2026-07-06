<script lang="ts">
  import Notice from "$lib/components/ui/Notice.svelte";
  import TextField from "$lib/components/ui/TextField.svelte";
  import type { TitleSearchResult, StreamSearchResult } from "$lib/searchApi";
  import { filterStreams, type StreamFilterMode } from "$lib/streamFilters";
  import StreamResultItem from "./StreamResultItem.svelte";

  export let selectedTitle: TitleSearchResult;
  export let searchingStreams: boolean;
  export let searchingEpisodeStreams: boolean;
  export let streamResults: StreamSearchResult[];
  export let pendingStreamKeys: string[];
  export let streamActionMessage: string;
  export let error: string;

  export let onStreamFilterChange: (filter: string) => Promise<void>;
  export let onAddStream: (stream: StreamSearchResult) => Promise<void>;
  export let onRemoveStream: (stream: StreamSearchResult) => Promise<void>;
  export let onBack: () => void;

  let filterRegex = "";
  let filterMode: StreamFilterMode = "all";
  let visibleLimit = 100;
  let lookupTimer: ReturnType<typeof setTimeout> | null = null;
  let lastLookupFilter = "";

  $: queueEpisodeLookup(filterRegex);
  $: filteredResult = filterStreams(streamResults, filterRegex, filterMode);
  $: visibleStreams = filteredResult.streams;
  $: displayedStreams = visibleStreams.slice(0, visibleLimit);
  $: canShowMore = displayedStreams.length < visibleStreams.length;

  function queueEpisodeLookup(value: string) {
    if (selectedTitle.media_type !== "series") return;
    const trimmed = value.trim();
    if (!trimmed || trimmed === lastLookupFilter) return;
    if (lookupTimer !== null) {
      clearTimeout(lookupTimer);
    }
    lookupTimer = setTimeout(() => {
      lastLookupFilter = trimmed;
      void onStreamFilterChange(trimmed);
    }, 350);
  }
</script>

<div class="streams-header">
  <button type="button" class="back-btn" on:click={onBack}> ← Back to Search </button>
</div>

<div class="selected-details">
  {#if selectedTitle.poster_url}
    <img class="mini-poster" src={selectedTitle.poster_url} alt={selectedTitle.title} />
  {/if}
  <div class="details-text">
    <h2>{selectedTitle.title}</h2>
    {#if selectedTitle.year}
      <span class="year-badge">{selectedTitle.year}</span>
    {/if}
    <p class="overview">{selectedTitle.overview}</p>
  </div>
</div>

{#if error}
  <Notice variant="error">{error}</Notice>
{/if}

{#if streamActionMessage}
  <Notice variant="success">{streamActionMessage}</Notice>
{/if}

{#if searchingStreams}
  <div class="loading-state">
    <div class="spinner"></div>
    <p>Discovering stream candidates...</p>
  </div>
{:else if streamResults.length > 0}
  <div class="filter-panel">
    <TextField bind:value={filterRegex} label="Filter" placeholder="s01e02, s01, remux, 1080p|4k" />
    <div class="filter-count">
      Showing {displayedStreams.length} of {visibleStreams.length}
    </div>
  </div>

  {#if selectedTitle.media_type === "series"}
    <div class="mode-chips" aria-label="Stream type filters">
      <button
        class:active={filterMode === "all"}
        type="button"
        on:click={() => (filterMode = "all")}
      >
        All
      </button>
      <button
        class:active={filterMode === "single"}
        type="button"
        on:click={() => (filterMode = "single")}
      >
        Single
      </button>
      <button
        class:active={filterMode === "complete"}
        type="button"
        on:click={() => (filterMode = "complete")}
      >
        Complete
      </button>
      {#if searchingEpisodeStreams}
        <span>Loading episode matches...</span>
      {/if}
    </div>
  {/if}

  <div class="streams-list">
    {#each displayedStreams as stream (stream.stream_key)}
      <StreamResultItem
        {stream}
        pending={pendingStreamKeys.includes(stream.stream_key)}
        onAdd={onAddStream}
        onRemove={onRemoveStream}
      />
    {/each}
  </div>

  {#if canShowMore}
    <button type="button" class="show-more" on:click={() => (visibleLimit += 100)}>
      Show more
    </button>
  {/if}
{:else}
  <p class="no-results">No stream candidates found for this selection.</p>
{/if}

<style>
  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 64px 0;
    color: #5b6a61;
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid #eef3f0;
    border-top: 3px solid #1f5b42;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: 16px;
  }

  @keyframes spin {
    0% {
      transform: rotate(0deg);
    }
    100% {
      transform: rotate(360deg);
    }
  }

  .streams-header {
    margin-bottom: 16px;
  }

  .back-btn {
    background: transparent;
    border: none;
    color: #1f5b42;
    font-weight: 600;
    cursor: pointer;
    font-size: 14px;
    padding: 0;
  }

  .back-btn:hover {
    text-decoration: underline;
  }

  .selected-details {
    display: flex;
    gap: 20px;
    background: #ffffff;
    border: 1px solid #d7ded9;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 24px;
    align-items: flex-start;
  }

  .mini-poster {
    width: 80px;
    border-radius: 6px;
    object-fit: cover;
  }

  .details-text {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
  }

  .details-text h2 {
    margin: 0 0 6px;
    font-size: 22px;
    font-weight: 800;
  }

  .year-badge {
    background: #eef3f0;
    color: #1f5b42;
    font-size: 11px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    margin-bottom: 8px;
  }

  .overview {
    margin: 0;
    font-size: 12px;
    color: #5b6a61;
    line-height: 1.4;
  }

  .filter-panel {
    display: flex;
    align-items: flex-end;
    gap: 16px;
    background: #ffffff;
    border: 1px solid #d7ded9;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 16px;
  }

  .filter-panel :global(label) {
    flex: 1;
  }

  .filter-count {
    height: 38px;
    display: flex;
    align-items: center;
    color: #526057;
    font-size: 12px;
    font-weight: 700;
    white-space: nowrap;
  }

  .mode-chips {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }

  .mode-chips button {
    height: 28px;
    border: 1px solid #bdc8c2;
    border-radius: 6px;
    background: #ffffff;
    color: #24352d;
    cursor: pointer;
    font-size: 12px;
    font-weight: 700;
    padding: 0 10px;
  }

  .mode-chips button.active {
    border-color: #1f5b42;
    background: #1f5b42;
    color: #ffffff;
  }

  .mode-chips span {
    color: #526057;
    font-size: 12px;
    font-weight: 700;
  }

  .streams-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .show-more {
    width: 100%;
    height: 40px;
    margin-top: 14px;
    border: 1px solid #bdc8c2;
    border-radius: 6px;
    background: #ffffff;
    color: #24352d;
    cursor: pointer;
    font-weight: 700;
  }

  .no-results {
    text-align: center;
    color: #5b6a61;
    padding: 48px 0;
  }

  @media (max-width: 860px) {
    .filter-panel {
      max-width: 100%;
      flex-direction: column;
      align-items: stretch;
    }

    .filter-count {
      height: auto;
    }
  }
</style>
