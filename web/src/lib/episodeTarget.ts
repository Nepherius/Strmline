export interface ParsedEpisodeTarget {
  season: number;
  episode: number;
}

export function parseEpisodeTarget(value: string): ParsedEpisodeTarget | null {
  const match =
    /\bs(\d{1,2})\s*e(\d{1,3})\b/i.exec(value) ?? /\b(\d{1,2})x(\d{1,3})\b/i.exec(value);

  if (match === null) {
    return null;
  }

  const season = Number.parseInt(match[1] ?? "", 10);
  const episode = Number.parseInt(match[2] ?? "", 10);
  if (season < 1 || episode < 1) {
    return null;
  }
  return { season, episode };
}
