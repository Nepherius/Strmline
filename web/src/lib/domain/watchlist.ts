export function watchlistCleanupTarget(
  mediaType: "movie" | "series",
  tmdbId: number,
  streamSelected: boolean,
  watchlistedItems: readonly { media_type: "movie" | "series"; tmdb_id: number }[],
): { media_type: "movie" | "series"; tmdb_id: number } | null {
  if (tmdbId <= 0 || !streamSelected) return null;
  return (
    watchlistedItems.find((item) => item.media_type === mediaType && item.tmdb_id === tmdbId) ??
    null
  );
}
