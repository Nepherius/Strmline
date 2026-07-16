export function watchlistCleanupTarget(
  mediaType: string,
  tmdbId: number,
  streamSelected: boolean,
  watchlistedTmdbIds: readonly number[],
): number | null {
  if (mediaType !== "series" || tmdbId <= 0 || !streamSelected) return null;
  return watchlistedTmdbIds.includes(tmdbId) ? tmdbId : null;
}
