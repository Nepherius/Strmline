import type { StreamSearchResult } from "./searchApi";

export function sortStreamResults(streams: StreamSearchResult[]): StreamSearchResult[] {
  return [...streams].sort((a, b) => {
    const cachedDelta = cacheRank(b) - cacheRank(a);
    if (cachedDelta !== 0) return cachedDelta;
    return (b.parsed.size_bytes ?? 0) - (a.parsed.size_bytes ?? 0);
  });
}

function cacheRank(stream: StreamSearchResult): number {
  if (stream.cached === true) return 3;
  if (stream.provider_label === "Instant TB") return 3;
  if (stream.provider_label === "Cast TB") return 2;
  if (stream.provider_label === "DL with TB") return 1;
  return 0;
}
