<script lang="ts">
  import { onMount } from "svelte";
  import { loadSettings } from "$lib/api/settings";
  import {
    addStreamToTorBox,
    removeStreamFromTorBox,
    searchTitles,
    searchStreams,
  } from "$lib/api/search";
  import type { StreamSearchResult, TitleSearchResult } from "$lib/domain/search/types";
  import { parseEpisodeTarget } from "$lib/domain/search/episodeTarget";
  import { sortStreamResults } from "$lib/domain/search/streamSort";
  import SearchView from "./SearchView.svelte";

  let mode: "title" | "streams" = "title";
  let aiostreamsConfigured = false;
  let tmdbConfigured = false;
  let query = "";
  let lastSubmittedQuery = "";

  let searchingTitles = false;
  let titleResults: TitleSearchResult[] = [];

  let selectedTitle: TitleSearchResult | null = null;

  let searchingStreams = false;
  let searchingEpisodeStreams = false;
  let streamResults: StreamSearchResult[] = [];
  let episodeLookupKeys: string[] = [];
  let pendingStreamKeys: string[] = [];
  let streamActionMessage = "";

  let error = "";
  let loadingSettings = true;

  onMount(async () => {
    try {
      const settings = await loadSettings();
      aiostreamsConfigured = settings.aiostreams_configured;
      tmdbConfigured = settings.tmdb_configured;
    } catch (caughtError) {
      error = caughtError instanceof Error ? caughtError.message : "Failed to load settings.";
    } finally {
      loadingSettings = false;
    }
  });

  async function handleTitleSearch() {
    const trimmedQuery = query.trim();
    if (!trimmedQuery) return;
    lastSubmittedQuery = trimmedQuery;
    error = "";
    searchingTitles = true;
    titleResults = [];
    try {
      const res = await searchTitles(trimmedQuery);
      if (res.ok) {
        titleResults = res.results;
        // If it's a direct IMDB ID, we transition immediately to the streams view
        const firstResult = titleResults[0];
        if (titleResults.length === 1 && firstResult?.tmdb_id === 0) {
          await handleSelectTitle(firstResult);
        }
      } else {
        error = res.message;
      }
    } catch (caughtError) {
      error = caughtError instanceof Error ? caughtError.message : "Title search failed.";
    } finally {
      searchingTitles = false;
    }
  }

  async function handleSelectTitle(title: TitleSearchResult) {
    selectedTitle = title;
    mode = "streams";
    episodeLookupKeys = [];
    await fetchStreams();
  }

  async function fetchStreams() {
    if (!selectedTitle) return;
    error = "";
    streamActionMessage = "";
    searchingStreams = true;
    streamResults = [];
    try {
      const res = await searchStreams(
        selectedTitle.media_type,
        selectedTitle.imdb_id,
        selectedTitle.tmdb_id !== 0 ? selectedTitle.tmdb_id : null,
      );
      if (res.ok) {
        streamResults = sortStreamResults(dedupeStreams(res.streams));
      } else {
        error = res.message;
      }
    } catch (caughtError) {
      error = caughtError instanceof Error ? caughtError.message : "Streams search failed.";
    } finally {
      searchingStreams = false;
    }
  }

  async function handleStreamFilterChange(filter: string) {
    if (selectedTitle?.media_type !== "series") return;
    const target = parseEpisodeTarget(filter);
    if (target === null) return;

    const titleKey = selectedTitle.imdb_id ?? String(selectedTitle.tmdb_id);
    const lookupKey = `${titleKey}:${String(target.season)}:${String(target.episode)}`;
    if (episodeLookupKeys.includes(lookupKey)) return;
    episodeLookupKeys = [...episodeLookupKeys, lookupKey];

    searchingEpisodeStreams = true;
    try {
      const res = await searchStreams(
        selectedTitle.media_type,
        selectedTitle.imdb_id,
        selectedTitle.tmdb_id !== 0 ? selectedTitle.tmdb_id : null,
        target.season,
        target.episode,
      );
      if (res.ok) {
        streamResults = sortStreamResults(dedupeStreams([...streamResults, ...res.streams]));
      }
    } catch {
      episodeLookupKeys = episodeLookupKeys.filter((key) => key !== lookupKey);
    } finally {
      searchingEpisodeStreams = false;
    }
  }

  async function handleAddStream(stream: StreamSearchResult) {
    if (!selectedTitle || pendingStreamKeys.includes(stream.stream_key)) return;
    error = "";
    streamActionMessage = "";
    pendingStreamKeys = [...pendingStreamKeys, stream.stream_key];
    try {
      const res = await addStreamToTorBox({
        media_type: selectedTitle.media_type,
        imdb_id: selectedTitle.imdb_id,
        tmdb_id: selectedTitle.tmdb_id !== 0 ? selectedTitle.tmdb_id : null,
        season: stream.season,
        episode: stream.episode,
        stream_key: stream.stream_key,
        add_only_if_cached: true,
      });
      if (res.ok) {
        setStreamSelected(res.stream_key, res.selected);
        streamActionMessage = res.message;
      } else {
        error = res.message;
      }
    } catch (caughtError) {
      error = caughtError instanceof Error ? caughtError.message : "Could not add stream.";
    } finally {
      pendingStreamKeys = pendingStreamKeys.filter((key) => key !== stream.stream_key);
    }
  }

  async function handleRemoveStream(stream: StreamSearchResult) {
    if (pendingStreamKeys.includes(stream.stream_key)) return;
    error = "";
    streamActionMessage = "";
    pendingStreamKeys = [...pendingStreamKeys, stream.stream_key];
    try {
      const res = await removeStreamFromTorBox(stream.stream_key);
      if (res.ok) {
        setStreamSelected(res.stream_key, res.selected);
        streamActionMessage = res.message;
      } else {
        error = res.message;
      }
    } catch (caughtError) {
      error = caughtError instanceof Error ? caughtError.message : "Could not remove stream.";
    } finally {
      pendingStreamKeys = pendingStreamKeys.filter((key) => key !== stream.stream_key);
    }
  }

  function dedupeStreams(streams: StreamSearchResult[]): StreamSearchResult[] {
    let seen: string[] = [];
    const unique: StreamSearchResult[] = [];
    for (const stream of streams) {
      const key = stream.stream_key;
      if (seen.includes(key)) continue;
      seen = [...seen, key];
      unique.push(stream);
    }
    return unique;
  }

  function setStreamSelected(streamKey: string, selected: boolean) {
    streamResults = streamResults.map((stream) =>
      stream.stream_key === streamKey ? { ...stream, selected } : stream,
    );
  }

  function handleBackToSearch() {
    mode = "title";
    selectedTitle = null;
    streamResults = [];
    episodeLookupKeys = [];
    error = "";
    streamActionMessage = "";
  }
</script>

<SearchView
  {mode}
  {aiostreamsConfigured}
  {tmdbConfigured}
  {loadingSettings}
  bind:query
  {searchingTitles}
  {titleResults}
  {lastSubmittedQuery}
  {selectedTitle}
  {searchingStreams}
  {searchingEpisodeStreams}
  {streamResults}
  {pendingStreamKeys}
  {streamActionMessage}
  {error}
  onSearch={handleTitleSearch}
  onSelectTitle={handleSelectTitle}
  onStreamFilterChange={handleStreamFilterChange}
  onAddStream={handleAddStream}
  onRemoveStream={handleRemoveStream}
  onBack={handleBackToSearch}
/>
