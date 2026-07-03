import { describe, expect, it } from "vitest";

import {
  duplicateFileCount,
  filterFiles,
  sortFiles,
  type LibrarySummary,
} from "./lib/librarySummary";

describe("frontend tooling", () => {
  it("runs the Vitest suite", () => {
    expect("Strmline").toBe("Strmline");
  });
});

describe("library summary helpers", () => {
  const files = [
    {
      category: "shows" as const,
      title: "Reborn Rookie",
      relative_path: "shows/Reborn Rookie/Season 01/Reborn Rookie - S01E04.strm",
    },
    {
      category: "movies" as const,
      title: "Project Hail Mary",
      relative_path: "movies/Project Hail Mary (2026)/Project Hail Mary (2026).strm",
    },
  ];

  it("filters files by category and query", () => {
    expect(filterFiles(files, "hail", "movies")).toEqual([files[1]]);
  });

  it("sorts files by title", () => {
    expect(sortFiles(files, "title", "asc").map((file) => file.title)).toEqual([
      "Project Hail Mary",
      "Reborn Rookie",
    ]);
  });

  it("counts duplicate group files", () => {
    const summary: LibrarySummary = {
      configured: true,
      root: "/tmp/library",
      exists: true,
      total_files: 2,
      category_counts: { movies: 2, shows: 0, anime: 0 },
      files,
      duplicate_groups: [{ key: "movies:duplicate", files }],
    };

    expect(duplicateFileCount(summary)).toBe(2);
  });
});
