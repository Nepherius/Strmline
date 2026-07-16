import { fetchJson, fetchNoContent } from "$lib/api/client";
import type { TitleSearchResult } from "$lib/domain/search/types";

export interface WatchlistItem {
  id: number;
  tmdb_id: number;
  imdb_id: string | null;
  title: string;
  year: string | null;
  overview: string;
  poster_url: string | null;
  media_type: "series";
}

export function loadWatchlist(): Promise<WatchlistItem[]> {
  return fetchJson<WatchlistItem[]>("/api/watchlist");
}

export function addTitleToWatchlist(title: TitleSearchResult): Promise<WatchlistItem> {
  return fetchJson<WatchlistItem>("/api/watchlist", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      tmdb_id: title.tmdb_id,
      imdb_id: title.imdb_id,
      title: title.title,
      year: title.year,
      overview: title.overview,
      poster_url: title.poster_url,
      media_type: "series",
    }),
  });
}

export function removeTitleFromWatchlist(tmdbId: number): Promise<void> {
  return fetchNoContent(`/api/watchlist/${String(tmdbId)}`, { method: "DELETE" });
}
