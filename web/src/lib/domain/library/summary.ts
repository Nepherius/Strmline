export type LibraryCategory = "movies" | "shows" | "anime";
export type LibraryDisplayCategory = LibraryCategory | "watchlist";
export type LibraryHealthStatus = "ready" | "recoverable" | "unavailable" | "unknown";

export interface LibraryHealthSummary {
  status: LibraryHealthStatus;
  total: number;
  ready: number;
  recoverable: number;
  unavailable: number;
  unknown: number;
  checked_at: string | null;
}

export interface LibraryFile {
  category: LibraryCategory;
  title: string;
  relative_path: string;
}

export interface LibraryDuplicateGroup {
  key: string;
  files: LibraryFile[];
}

export interface LibraryEntry {
  key: string;
  category: LibraryDisplayCategory;
  title: string;
  relative_path: string;
  file_count: number;
  poster_url?: string | null;
  watchlist_id?: number;
  tmdb_id?: number | null;
  media_item_id?: number | null;
  media_type?: "movie" | "series";
  imdb_id?: string | null;
  year?: string | null;
  overview?: string;
  health?: LibraryHealthSummary;
}

export interface LibrarySummary {
  configured: boolean;
  root: string | null;
  exists: boolean;
  total_files: number;
  category_counts: Record<LibraryCategory, number>;
  files: LibraryFile[];
  entries: LibraryEntry[];
  duplicate_groups: LibraryDuplicateGroup[];
}

export interface LibraryEntryPage {
  entries: LibraryEntry[];
  limit: number;
  total: number | null;
  has_more: boolean;
  next_cursor: string | null;
  total_files: number | null;
  category_counts: Record<LibraryCategory, number> | null;
}

export interface LibraryValidationIssue {
  code: string;
  message: string;
  relative_path: string | null;
}

export interface LibraryValidation {
  configured: boolean;
  root: string | null;
  exists: boolean;
  ok: boolean;
  total_files: number;
  category_counts: Record<LibraryCategory, number>;
  warnings: LibraryValidationIssue[];
  errors: LibraryValidationIssue[];
}

export interface LibraryDiagnostics extends LibraryValidation {
  duplicate_groups: LibraryDuplicateGroup[];
  duplicate_file_count: number;
}

export type SortKey = "title" | "category" | "relative_path";
export type SortDirection = "asc" | "desc";

export const categoryLabels: Record<LibraryDisplayCategory, string> = {
  movies: "Movies",
  shows: "Shows",
  anime: "Anime",
  watchlist: "Watchlist",
};

export const healthLabels: Record<LibraryHealthStatus, string> = {
  ready: "Ready",
  recoverable: "Recoverable",
  unavailable: "Unavailable",
  unknown: "Unknown",
};

export function libraryHealthTooltip(
  health: LibraryHealthSummary | undefined,
  checking = false,
): string {
  if (checking) return "Checking — Strmline is checking this title against TorBox.";
  if (!health || health.status === "unknown") {
    return "Unknown — Availability has not been checked, or a file has no torrent hash to check.";
  }
  if (health.status === "unavailable") {
    return `Unavailable — ${String(health.unavailable)} of ${String(health.total)} files are absent from your TorBox account and its cache.`;
  }
  if (health.status === "recoverable") {
    return `Recoverable — ${String(health.recoverable)} of ${String(health.total)} files are absent from your TorBox account but remain cached and can be restored.`;
  }
  return `Ready — All ${String(health.total)} files are present in your TorBox account.`;
}

export function filterFiles(
  files: LibraryEntry[],
  query: string,
  category: LibraryDisplayCategory | "all",
): LibraryEntry[] {
  const normalizedQuery = query.trim().toLowerCase();
  return files.filter((file) => {
    const categoryMatches = category === "all" || file.category === category;
    const queryMatches =
      normalizedQuery.length === 0 ||
      file.title.toLowerCase().includes(normalizedQuery) ||
      file.relative_path.toLowerCase().includes(normalizedQuery);
    return categoryMatches && queryMatches;
  });
}

export function sortFiles(
  files: LibraryEntry[],
  sortKey: SortKey,
  direction: SortDirection,
): LibraryEntry[] {
  const multiplier = direction === "asc" ? 1 : -1;
  return [...files].sort((left, right) => {
    return left[sortKey].localeCompare(right[sortKey]) * multiplier;
  });
}

export function duplicateFileCount(summary: LibrarySummary): number {
  return summary.duplicate_groups.reduce((total, group) => total + group.files.length, 0);
}
