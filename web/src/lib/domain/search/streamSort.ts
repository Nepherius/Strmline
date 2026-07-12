import type { StreamSearchResult } from "$lib/domain/search/types";

export type StreamSortMode = "balanced" | "cached" | "quality" | "size";

export function sortStreamResults(
  streams: StreamSearchResult[],
  mode: StreamSortMode = "balanced",
): StreamSearchResult[] {
  return [...streams].sort((a, b) => {
    for (const compare of comparatorsForMode(mode)) {
      const delta = compare(a, b);
      if (delta !== 0) return delta;
    }
    return a.title.localeCompare(b.title);
  });
}

type StreamComparator = (left: StreamSearchResult, right: StreamSearchResult) => number;

function comparatorsForMode(mode: StreamSortMode): StreamComparator[] {
  if (mode === "balanced") return [compareCache, compareBalanced, compareQuality, compareSize];
  if (mode === "quality") return [compareCache, compareQuality, compareSize];
  if (mode === "size") return [compareCache, compareSize, compareQuality];
  return [compareCache, compareQuality, compareSize];
}

function compareCache(left: StreamSearchResult, right: StreamSearchResult): number {
  return cacheRank(right) - cacheRank(left);
}

function compareQuality(left: StreamSearchResult, right: StreamSearchResult): number {
  return qualityRank(right.parsed.quality) - qualityRank(left.parsed.quality);
}

function compareSize(left: StreamSearchResult, right: StreamSearchResult): number {
  return (right.parsed.size_bytes ?? 0) - (left.parsed.size_bytes ?? 0);
}

function compareBalanced(left: StreamSearchResult, right: StreamSearchResult): number {
  return balancedContentScore(right) - balancedContentScore(left);
}

function balancedContentScore(stream: StreamSearchResult): number {
  const quality = qualityRank(stream.parsed.quality) * 5;
  const sizeGiB = (stream.parsed.size_bytes ?? 0) / 1024 ** 3;
  const size = Math.min(sizeGiB, 100);
  return quality + size;
}

function cacheRank(stream: StreamSearchResult): number {
  if (stream.cached === true) return 3;
  const text = `${stream.provider_label ?? ""} ${stream.title}`.toLowerCase();
  if (CACHED_MARKER_PATTERN.test(text)) return 3;
  if (UNCACHED_MARKER_PATTERN.test(text)) return 0;
  if (text.includes("tb⚡")) return 3;
  if (text.includes("instant tb")) return 3;
  if (text.includes("cast tb") || text.includes("cast (tb")) return 2;
  if (text.includes("dl with tb")) return 1;
  return 0;
}

function qualityRank(quality: string | null): number {
  const value = quality?.toLowerCase() ?? "";
  if (value === "4k" || value === "2160p") return 5;
  if (value === "1440p") return 4;
  if (value === "1080p") return 3;
  if (value === "720p") return 2;
  if (value === "480p" || value === "360p") return 1;
  if (["cam", "ts", "scr"].includes(value)) return -1;
  return 0;
}

const CACHED_MARKER_PATTERN = /\[[^\]]*⚡[^\]]*\]/u;
const UNCACHED_MARKER_PATTERN = /\[[^\]]*⏳[^\]]*\]/u;
