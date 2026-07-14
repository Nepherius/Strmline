export type LibraryCategory = "movies" | "shows" | "anime";

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
  category: LibraryCategory;
  title: string;
  relative_path: string;
  file_count: number;
  poster_url?: string | null;
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

export type SortKey = "title" | "category" | "relative_path";
export type SortDirection = "asc" | "desc";

export const categoryLabels: Record<LibraryCategory, string> = {
  movies: "Movies",
  shows: "Shows",
  anime: "Anime",
};

export function filterFiles(
  files: LibraryEntry[],
  query: string,
  category: LibraryCategory | "all",
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

export function validationIssueCount(validation: LibraryValidation): number {
  return validation.errors.length + validation.warnings.length;
}
