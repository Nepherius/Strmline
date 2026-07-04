import { describe, expect, it } from "vitest";

import { normalizeApiBase } from "./lib/api";
import {
  duplicateFileCount,
  filterFiles,
  sortFiles,
  type LibrarySummary,
} from "./lib/librarySummary";
import {
  buildSettingsPayload,
  missingLabels,
  settingSourceLabel,
  settingsToFormValues,
} from "./lib/settings";
import { buildTmdbConnectionTestPayload, buildTorboxConnectionTestPayload } from "./lib/setupApi";

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

describe("api helpers", () => {
  it("normalizes API base URLs", () => {
    expect(normalizeApiBase(" http://127.0.0.1:8001/ ")).toBe("http://127.0.0.1:8001");
  });

  it("builds TorBox test payloads from typed keys", () => {
    expect(buildTorboxConnectionTestPayload(" typed-key ")).toEqual({
      torbox_api_key: "typed-key",
    });
    expect(buildTorboxConnectionTestPayload(" ")).toEqual({});
  });

  it("builds TMDB test payloads from typed keys", () => {
    expect(buildTmdbConnectionTestPayload(" tmdb-key ")).toEqual({
      tmdb_api_key: "tmdb-key",
    });
    expect(buildTmdbConnectionTestPayload(" ")).toEqual({});
  });
});

describe("settings helpers", () => {
  it("builds update payloads without empty secret fields", () => {
    expect(
      buildSettingsPayload({
        baseUrl: " http://127.0.0.1:8001 ",
        libraryRoot: "/tmp/strmline-library",
        torboxApiKey: "",
        tmdbApiKey: "tmdb",
        resolverToken: "",
      }),
    ).toEqual({
      base_url: "http://127.0.0.1:8001",
      library_root: "/tmp/strmline-library",
      tmdb_api_key: "tmdb",
    });
  });

  it("keeps persisted secrets out of form values", () => {
    expect(
      settingsToFormValues({
        base_url: "http://127.0.0.1:8001",
        library_root: "/tmp/strmline-library",
        torbox_configured: true,
        tmdb_configured: true,
        resolver_configured: true,
        base_url_source: "database",
        library_root_source: "database",
        torbox_source: "database",
        tmdb_source: "database",
        resolver_source: "database",
      }),
    ).toEqual({
      baseUrl: "http://127.0.0.1:8001",
      libraryRoot: "/tmp/strmline-library",
      torboxApiKey: "",
      tmdbApiKey: "",
      resolverToken: "",
    });
  });

  it("formats setup missing fields", () => {
    expect(missingLabels(["database_url", "torbox_api_key"])).toEqual(["Database", "TorBox key"]);
  });

  it("formats settings sources", () => {
    expect(settingSourceLabel("database")).toBe("Saved");
    expect(settingSourceLabel("environment")).toBe("Env");
    expect(settingSourceLabel(null)).toBe("Missing");
  });
});
