import type { StreamSearchResult } from "$lib/searchApi";

export type StreamFilterMode = "all" | "single" | "complete";

export interface StreamFilterResult {
  streams: StreamSearchResult[];
}

export function filterStreams(
  streams: StreamSearchResult[],
  pattern: string,
  mode: StreamFilterMode,
): StreamFilterResult {
  const trimmed = pattern.trim();
  const regex = compileFilterRegex(trimmed);
  const normalizedPattern = normalizeSearchText(trimmed);

  return {
    streams: streams.filter((stream) => {
      const text = searchableStreamText(stream);
      if (mode === "single" && !isSingleEpisodeStream(text)) {
        return false;
      }
      if (mode === "complete" && !isCompleteSeasonStream(text)) {
        return false;
      }
      if (!trimmed) {
        return true;
      }
      return regex?.test(text) === true || normalizeSearchText(text).includes(normalizedPattern);
    }),
  };
}

function compileFilterRegex(pattern: string): RegExp | null {
  try {
    return new RegExp(pattern, "i");
  } catch {
    return null;
  }
}

function searchableStreamText(stream: StreamSearchResult): string {
  return [
    stream.title,
    stream.parsed.quality,
    stream.parsed.codec,
    stream.parsed.hdr,
    stream.parsed.audio,
    stream.parsed.size_label,
    stream.parsed.source,
    stream.parsed.language,
    stream.provider_label,
  ]
    .filter((value): value is string => typeof value === "string" && value.trim().length > 0)
    .join(" ");
}

function normalizeSearchText(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function isSingleEpisodeStream(text: string): boolean {
  return /\bs\d{1,2}\s*e\d{1,3}\b/i.test(text) || /\b\d{1,2}x\d{1,3}\b/i.test(text);
}

function isCompleteSeasonStream(text: string): boolean {
  if (isSingleEpisodeStream(text)) {
    return false;
  }
  if (/\bincomplete\b/i.test(text)) {
    return false;
  }
  return (
    /\bcomplete\b/i.test(text) ||
    /\bseason\s+\d{1,2}\s+pack\b/i.test(text) ||
    /\bs\d{1,2}\s+pack\b/i.test(text) ||
    /\bs\d{1,2}\b/i.test(text)
  );
}
