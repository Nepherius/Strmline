<script lang="ts">
  import Notice from "$lib/components/ui/Notice.svelte";
  import TextField from "$lib/components/ui/TextField.svelte";
  import UiButton from "$lib/components/ui/UiButton.svelte";
  import type { TitleSearchResult } from "$lib/searchApi";

  export let query: string;
  export let searchingTitles: boolean;
  export let titleResults: TitleSearchResult[];
  export let lastSubmittedQuery: string;
  export let tmdbConfigured: boolean;
  export let error: string;

  export let onSearch: () => Promise<void>;
  export let onSelectTitle: (title: TitleSearchResult) => Promise<void>;
</script>

{#if error}
  <Notice variant="error">{error}</Notice>
{/if}

{#if !tmdbConfigured}
  <Notice>Title search requires TMDB. Paste an IMDB ID to search AIOStreams directly.</Notice>
{/if}

<div class="search-form-wrap">
  <form class="search-bar" on:submit|preventDefault={onSearch}>
    <div class="input-wrap">
      <TextField
        bind:value={query}
        label=""
        placeholder={tmdbConfigured
          ? "Search by title (e.g. Inception) or paste IMDB ID (e.g. tt1375666)"
          : "Paste IMDB ID (e.g. tt1375666)"}
      />
    </div>
    <UiButton type="submit" disabled={searchingTitles}>
      {searchingTitles ? "Searching..." : "Search"}
    </UiButton>
  </form>
</div>

{#if searchingTitles}
  <div class="loading-state">
    <div class="spinner"></div>
    <p>Searching titles...</p>
  </div>
{:else if titleResults.length > 0}
  <div class="results-grid">
    {#each titleResults as result (result.imdb_id ?? String(result.tmdb_id))}
      <button type="button" class="title-card" on:click={() => onSelectTitle(result)}>
        <div class="poster-wrap">
          {#if result.poster_url}
            <img src={result.poster_url} alt={result.title} />
          {:else}
            <div class="poster-placeholder">🎬</div>
          {/if}
        </div>
        <div class="card-info">
          <h3>{result.title}</h3>
          <div class="badges">
            <span class="type-badge">{result.media_type === "series" ? "Show" : "Movie"}</span>
            {#if result.year}
              <span class="year-badge">{result.year}</span>
            {/if}
          </div>
          <p class="overview">{result.overview || "No overview available."}</p>
        </div>
      </button>
    {/each}
  </div>
{:else if lastSubmittedQuery !== ""}
  <p class="no-results">No titles found. Try adjusting your query.</p>
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

  .search-form-wrap {
    margin-top: 24px;
    margin-bottom: 32px;
    background: #ffffff;
    border: 1px solid #d7ded9;
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
  }

  .search-bar {
    display: flex;
    align-items: flex-end;
    gap: 16px;
  }

  .input-wrap {
    flex: 1;
  }

  .input-wrap :global(.text-field) {
    margin-bottom: 0;
  }

  .results-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 20px;
  }

  .title-card {
    display: flex;
    text-align: left;
    background: #ffffff;
    border: 1px solid #d7ded9;
    border-radius: 12px;
    overflow: hidden;
    cursor: pointer;
    transition: all 0.2s ease;
    padding: 0;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
  }

  .title-card:hover {
    transform: translateY(-2px);
    border-color: #1f5b42;
    box-shadow: 0 4px 12px rgba(31, 91, 66, 0.06);
  }

  .poster-wrap {
    width: 90px;
    flex-shrink: 0;
    background: #f5f7f6;
  }

  .poster-wrap img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .poster-placeholder {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    color: #bdc8c2;
  }

  .card-info {
    padding: 16px;
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
  }

  .card-info h3 {
    margin: 0 0 6px;
    font-size: 15px;
    font-weight: 700;
    color: #15201b;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    width: 100%;
  }

  .badges {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 8px;
  }

  .type-badge,
  .year-badge {
    background: #eef3f0;
    color: #1f5b42;
    font-size: 11px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
  }

  .type-badge {
    background: #f5f7f6;
    color: #526057;
  }

  .overview {
    margin: 0;
    font-size: 12px;
    color: #5b6a61;
    line-height: 1.4;
    display: -webkit-box;
    line-clamp: 3;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .no-results {
    text-align: center;
    color: #5b6a61;
    padding: 48px 0;
  }

  @media (max-width: 860px) {
    .search-bar {
      flex-direction: column;
      align-items: stretch;
      gap: 12px;
    }
  }
</style>
