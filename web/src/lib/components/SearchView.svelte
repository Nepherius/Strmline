<script lang="ts">
  import AppShell from "$lib/components/ui/AppShell.svelte";
  import Notice from "$lib/components/ui/Notice.svelte";
  import PageHeader from "$lib/components/ui/PageHeader.svelte";
  import UiLink from "$lib/components/ui/UiLink.svelte";
  import type { TitleSearchResult, StreamSearchResult } from "$lib/searchApi";
  import TitleSearchView from "./TitleSearchView.svelte";
  import StreamResultsView from "./StreamResultsView.svelte";

  export let mode: "title" | "streams";
  export let aiostreamsConfigured: boolean;
  export let loadingSettings: boolean;
  export let query: string;

  export let searchingTitles: boolean;
  export let titleResults: TitleSearchResult[];

  export let selectedTitle: TitleSearchResult | null;

  export let searchingStreams: boolean;
  export let searchingEpisodeStreams: boolean;
  export let streamResults: StreamSearchResult[];
  export let pendingStreamKeys: string[];
  export let streamActionMessage: string;

  export let error: string;

  export let onSearch: () => Promise<void>;
  export let onSelectTitle: (title: TitleSearchResult) => Promise<void>;
  export let onStreamFilterChange: (filter: string) => Promise<void>;
  export let onAddStream: (stream: StreamSearchResult) => Promise<void>;
  export let onRemoveStream: (stream: StreamSearchResult) => Promise<void>;
  export let onBack: () => void;
</script>

<svelte:head>
  <title>Search — Strmline</title>
</svelte:head>

<AppShell>
  {#if loadingSettings}
    <div class="loading-state">
      <div class="spinner"></div>
      <p>Loading configuration...</p>
    </div>
  {:else if !aiostreamsConfigured}
    <PageHeader ariaLabel="Search navigation" title="Discover content">
      <svelte:fragment slot="actions">
        <UiLink href="/">Home</UiLink>
        <UiLink href="/setup">Setup</UiLink>
      </svelte:fragment>
    </PageHeader>
    <Notice variant="error">
      AIOStreams is not configured. Please go to the
      <UiLink href="/setup">Setup page</UiLink>
      to configure AIOStreams before searching.
    </Notice>
  {:else if mode === "title"}
    <TitleSearchView
      bind:query
      {searchingTitles}
      {titleResults}
      {error}
      {onSearch}
      {onSelectTitle}
    />
  {:else if mode === "streams" && selectedTitle}
    <StreamResultsView
      {selectedTitle}
      {searchingStreams}
      {searchingEpisodeStreams}
      {streamResults}
      {pendingStreamKeys}
      {streamActionMessage}
      {error}
      {onStreamFilterChange}
      {onAddStream}
      {onRemoveStream}
      {onBack}
    />
  {/if}
</AppShell>

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
</style>
