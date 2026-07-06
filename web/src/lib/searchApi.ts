import { fetchJson } from "$lib/api";

export interface TitleSearchResult {
  tmdb_id: number;
  imdb_id: string | null;
  title: string;
  year: string | null;
  overview: string;
  poster_url: string | null;
  media_type: string;
}

export interface TitleSearchResponse {
  ok: boolean;
  message: string;
  results: TitleSearchResult[];
}

export interface ParsedStreamResponse {
  quality: string | null;
  codec: string | null;
  hdr: string | null;
  audio: string | null;
  size_bytes: number | null;
  size_label: string | null;
  source: string | null;
  language: string | null;
}

export interface StreamSearchResult {
  stream_key: string;
  title: string;
  season: number | null;
  episode: number | null;
  parsed: ParsedStreamResponse;
  cached: boolean | null;
  has_url: boolean;
  has_info_hash: boolean;
  addable: boolean;
  selected: boolean;
  provider_label: string | null;
  seeders: number | null;
}

export interface StreamSearchResponse {
  ok: boolean;
  message: string;
  stream_count: number;
  streams: StreamSearchResult[];
}

export interface StreamActionPayload {
  media_type: string;
  imdb_id?: string | null;
  tmdb_id?: number | null;
  season?: number | null;
  episode?: number | null;
  stream_key: string;
  add_only_if_cached?: boolean;
}

export interface StreamActionResponse {
  ok: boolean;
  message: string;
  stream_key: string;
  selected: boolean;
  torbox_torrent_id: string | null;
  auto_sync_status: string | null;
  auto_sync_run_id: number | null;
}

export function searchTitles(query: string): Promise<TitleSearchResponse> {
  return fetchJson<TitleSearchResponse>("/api/search/titles", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ query }),
  });
}

export function searchStreams(
  mediaType: string,
  imdbId?: string | null,
  tmdbId?: number | null,
  season?: number | null,
  episode?: number | null,
): Promise<StreamSearchResponse> {
  const body: Record<string, string | number> = { media_type: mediaType };
  if (imdbId) body["imdb_id"] = imdbId;
  if (tmdbId) body["tmdb_id"] = tmdbId;
  if (season !== undefined && season !== null) body["season"] = season;
  if (episode !== undefined && episode !== null) body["episode"] = episode;

  return fetchJson<StreamSearchResponse>("/api/search/streams", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function addStreamToTorBox(
  payload: StreamActionPayload,
): Promise<StreamActionResponse> {
  return fetchJson<StreamActionResponse>("/api/search/streams/add", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function removeStreamFromTorBox(streamKey: string): Promise<StreamActionResponse> {
  return fetchJson<StreamActionResponse>("/api/search/streams/remove", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ stream_key: streamKey }),
  });
}
