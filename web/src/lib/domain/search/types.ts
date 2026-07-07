export interface TitleSearchResult {
  tmdb_id: number;
  imdb_id: string | null;
  title: string;
  year: string | null;
  overview: string;
  poster_url: string | null;
  media_type: string;
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
