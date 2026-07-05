import { describe, expect, it } from "vitest";

import { fetchJson } from "./lib/api";
import {
  duplicateFileCount,
  filterFiles,
  sortFiles,
  validationIssueCount,
  type LibrarySummary,
  type LibraryValidation,
} from "./lib/librarySummary";
import {
  buildSettingsPayload,
  missingLabels,
  settingSourceLabel,
  settingsToFormValues,
} from "./lib/settings";
import {
  buildAioStreamsTestPayload,
  buildTmdbConnectionTestPayload,
  buildTorboxConnectionTestPayload,
} from "./lib/setupApi";

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

  it("counts validation issues", () => {
    const validation: LibraryValidation = {
      configured: true,
      root: "/tmp/library",
      exists: true,
      ok: false,
      total_files: 1,
      category_counts: { movies: 1, shows: 0, anime: 0 },
      warnings: [
        { code: "category_folder_missing", message: "shows missing", relative_path: "shows" },
      ],
      errors: [{ code: "strm_url_invalid", message: "bad url", relative_path: "movies/bad.strm" }],
    };

    expect(validationIssueCount(validation)).toBe(2);
  });
});

describe("api helpers", () => {
  it("uses same-origin API paths", async () => {
    const originalFetch = globalThis.fetch;
    let requestedPath = "";
    globalThis.fetch = (input: RequestInfo | URL) => {
      requestedPath = requestPath(input);
      return Promise.resolve(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    };
    try {
      await fetchJson("/api/health");
    } finally {
      globalThis.fetch = originalFetch;
    }
    expect(requestedPath).toBe("/api/health");
  });

  it("surfaces API error detail messages", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = () =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "Resolver token is required." }), {
          status: 400,
          headers: { "content-type": "application/json" },
        }),
      );
    try {
      await expect(fetchJson("/api/sync/run")).rejects.toThrow("Resolver token is required.");
    } finally {
      globalThis.fetch = originalFetch;
    }
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

  it("builds AIOStreams test payloads from typed values", () => {
    expect(
      buildAioStreamsTestPayload(" https://aio.example/manifest.json ", " movie ", " tt0133093 "),
    ).toEqual({
      base_url: "https://aio.example/manifest.json",
      media_type: "movie",
      media_id: "tt0133093",
    });
    expect(buildAioStreamsTestPayload(" ", "movie", "tt0133093")).toEqual({
      media_type: "movie",
      media_id: "tt0133093",
    });
    expect(buildAioStreamsTestPayload("https://aio.example/manifest.json", "movie", " ")).toEqual({
      base_url: "https://aio.example/manifest.json",
    });
  });
});

function requestPath(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

describe("settings helpers", () => {
  it("builds update payloads without empty secret fields", () => {
    expect(
      buildSettingsPayload({
        baseUrl: " http://127.0.0.1:8001 ",
        moviesEnabled: true,
        showsEnabled: false,
        animeEnabled: true,
        playbackMode: "direct",
        syncIntervalMinutes: "120",
        torboxApiKey: "",
        tmdbApiKey: "tmdb",
        resolverToken: "",
        aiostreamsBaseUrl: " https://aio.example/manifest.json ",
        aiostreamsMediaType: "movie",
        aiostreamsMediaId: "tt0133093",
      }),
    ).toEqual({
      base_url: "http://127.0.0.1:8001",
      movies_enabled: true,
      shows_enabled: false,
      anime_enabled: true,
      playback_mode: "direct",
      sync_interval_minutes: 120,
      tmdb_api_key: "tmdb",
      aiostreams_base_url: "https://aio.example/manifest.json",
    });
  });

  it("keeps persisted secrets out of form values", () => {
    expect(
      settingsToFormValues({
        base_url: "http://127.0.0.1:8001",
        library_root: "/tmp/strmline-library",
        movies_enabled: true,
        shows_enabled: false,
        anime_enabled: true,
        playback_mode: "direct",
        sync_interval_minutes: 120,
        torbox_configured: true,
        tmdb_configured: true,
        resolver_configured: true,
        aiostreams_configured: true,
        base_url_source: "database",
        library_root_source: "database",
        torbox_source: "database",
        tmdb_source: "database",
        resolver_source: "database",
        aiostreams_source: "database",
      }),
    ).toEqual({
      baseUrl: "http://127.0.0.1:8001",
      moviesEnabled: true,
      showsEnabled: false,
      animeEnabled: true,
      playbackMode: "direct",
      syncIntervalMinutes: "120",
      torboxApiKey: "",
      tmdbApiKey: "",
      resolverToken: "",
      aiostreamsBaseUrl: "",
      aiostreamsMediaType: "movie",
      aiostreamsMediaId: "",
    });
  });

  it("formats setup missing fields", () => {
    expect(missingLabels(["base_url", "database_url", "torbox_api_key"])).toEqual([
      "Database",
      "TorBox key",
    ]);
  });

  it("formats settings sources", () => {
    expect(settingSourceLabel("database")).toBe("Saved");
    expect(settingSourceLabel("environment")).toBe("Env");
    expect(settingSourceLabel(null)).toBe("Missing");
  });
});
