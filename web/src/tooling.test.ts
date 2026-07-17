import { describe, expect, it } from "vitest";
import packageMetadata from "../package.json";

import { fetchJson } from "./lib/api/client";
import { APP_VERSION } from "./lib/appVersion";
import { parseEpisodeTarget } from "./lib/domain/search/episodeTarget";
import {
  duplicateFileCount,
  filterFiles,
  sortFiles,
  type LibrarySummary,
} from "./lib/domain/library/summary";
import {
  buildSettingsPayload,
  missingLabels,
  settingSourceLabel,
  settingsToFormValues,
} from "./lib/domain/settings";
import {
  buildAioStreamsTestPayload,
  buildTmdbConnectionTestPayload,
  buildTorboxConnectionTestPayload,
} from "./lib/api/setup";
import { filterStreams } from "./lib/domain/search/streamFilters";
import type { StreamSearchResult } from "./lib/domain/search/types";
import { sortStreamResults } from "./lib/domain/search/streamSort";
import { watchlistCleanupTarget } from "./lib/domain/watchlist";

describe("frontend tooling", () => {
  it("runs the Vitest suite", () => {
    expect("Strmline").toBe("Strmline");
  });

  it("derives the displayed application version from package.json", () => {
    expect(APP_VERSION).toBe(packageMetadata.version);
  });
});

describe("watchlist lifecycle", () => {
  const series = { media_type: "series" as const, tmdb_id: 123 };
  const movie = { media_type: "movie" as const, tmdb_id: 123 };

  it("removes matching movies and series only after a confirmed stream add", () => {
    expect(watchlistCleanupTarget("series", 123, true, [series])).toEqual(series);
    expect(watchlistCleanupTarget("movie", 123, true, [movie])).toEqual(movie);
    expect(watchlistCleanupTarget("series", 123, false, [series])).toBeNull();
    expect(watchlistCleanupTarget("series", 456, true, [series])).toBeNull();
    expect(watchlistCleanupTarget("movie", 123, true, [series])).toBeNull();
  });
});

describe("library summary helpers", () => {
  const entries = [
    {
      key: "shows/Reborn Rookie",
      category: "shows" as const,
      title: "Reborn Rookie",
      relative_path: "shows/Reborn Rookie",
      file_count: 4,
    },
    {
      key: "movies/Project Hail Mary (2026)",
      category: "movies" as const,
      title: "Project Hail Mary",
      relative_path: "movies/Project Hail Mary (2026)",
      file_count: 1,
    },
  ];
  const duplicateFiles = [
    {
      category: "movies" as const,
      title: "Duplicate",
      relative_path: "movies/Duplicate/Duplicate.strm",
    },
    {
      category: "movies" as const,
      title: "Duplicate",
      relative_path: "movies/Duplicate.2024/Duplicate 2024.strm",
    },
  ];

  it("filters entries by category and query", () => {
    expect(filterFiles(entries, "hail", "movies")).toEqual([entries[1]]);
  });

  it("sorts entries by title", () => {
    expect(sortFiles(entries, "title", "asc").map((entry) => entry.title)).toEqual([
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
      files: duplicateFiles,
      entries,
      duplicate_groups: [{ key: "movies:duplicate", files: duplicateFiles }],
    };

    expect(duplicateFileCount(summary)).toBe(2);
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
    expect(buildAioStreamsTestPayload(" https://aio.example/manifest.json ")).toEqual({
      base_url: "https://aio.example/manifest.json",
    });
    expect(buildAioStreamsTestPayload(" ")).toEqual({});
  });
});

describe("stream search helpers", () => {
  const streams: StreamSearchResult[] = [
    streamFixture("Show.Name.S01E01.1080p.WEB-DL.mkv"),
    streamFixture("Show.Name.S01.1080p.BluRay.Complete.mkv"),
    streamFixture("Show.Name.S01.MULTi.1080p.Remux.Pack.mkv"),
    streamFixture("Show.Name.S01.720p.WEB-DL.mkv"),
  ];

  it("keeps all streams when the filter is blank", () => {
    expect(filterStreams(streams, "", "all").streams).toEqual(streams);
  });

  it("filters streams with normalized plain text", () => {
    expect(filterStreams(streams, "s01e01", "all").streams.map((stream) => stream.title)).toEqual([
      "Show.Name.S01E01.1080p.WEB-DL.mkv",
    ]);

    expect(
      filterStreams(streams, "s01 multi", "all").streams.map((stream) => stream.title),
    ).toEqual(["Show.Name.S01.MULTi.1080p.Remux.Pack.mkv"]);
  });

  it("filters streams with a case-insensitive regex", () => {
    expect(
      filterStreams(streams, "bluray|remux", "all").streams.map((stream) => stream.title),
    ).toEqual([
      "Show.Name.S01.1080p.BluRay.Complete.mkv",
      "Show.Name.S01.MULTi.1080p.Remux.Pack.mkv",
    ]);
  });

  it("falls back to plain text for invalid regex filters", () => {
    const result = filterStreams([streamFixture("Show.Name.[Group].mkv")], "[group", "all");

    expect(result.streams.map((stream) => stream.title)).toEqual(["Show.Name.[Group].mkv"]);
  });

  it("filters single episode streams", () => {
    expect(filterStreams(streams, "", "single").streams.map((stream) => stream.title)).toEqual([
      "Show.Name.S01E01.1080p.WEB-DL.mkv",
    ]);
  });

  it("filters complete season packs", () => {
    expect(filterStreams(streams, "", "complete").streams.map((stream) => stream.title)).toEqual([
      "Show.Name.S01.1080p.BluRay.Complete.mkv",
      "Show.Name.S01.MULTi.1080p.Remux.Pack.mkv",
      "Show.Name.S01.720p.WEB-DL.mkv",
    ]);
  });

  it("parses episode filters for lazy episode-specific lookups", () => {
    expect(parseEpisodeTarget("s01e02")).toEqual({ season: 1, episode: 2 });
    expect(parseEpisodeTarget("1x02 remux")).toEqual({ season: 1, episode: 2 });
    expect(parseEpisodeTarget("s01 pack")).toBeNull();
  });

  it("includes provider labels in stream regex filtering", () => {
    const torboxStream = streamFixture("Direct.mkv", null, true, false, "Instant TB");

    expect(filterStreams([torboxStream], "instant", "all").streams).toEqual([torboxStream]);
  });

  it("sorts stream results with balanced weighting", () => {
    const uncachedLarge = streamFixture("large", null, true, true, null, 90);
    const cachedSmall = streamFixture("cached-small", true, true, true, null, 5);
    const instantMedium = streamFixture("instant-medium", null, true, true, "Instant TB", 40);
    const uncachedMedium = streamFixture("medium", null, true, true, null, 40);

    // balanced keeps cached streams first, then blends quality + size within
    // each cache tier.
    expect(
      sortStreamResults([uncachedLarge, uncachedMedium, cachedSmall, instantMedium]).map(
        (stream) => stream.title,
      ),
    ).toEqual(["instant-medium", "cached-small", "large", "medium"]);
  });

  it("sorts stream results with cached sources first and then size", () => {
    const uncachedLarge = streamFixture("large", null, true, true, null, 90);
    const cachedSmall = streamFixture("cached-small", true, true, true, null, 5);
    const instantMedium = streamFixture("instant-medium", null, true, true, "Instant TB", 40);
    const uncachedMedium = streamFixture("medium", null, true, true, null, 40);

    expect(
      sortStreamResults([uncachedLarge, uncachedMedium, cachedSmall, instantMedium], "cached").map(
        (stream) => stream.title,
      ),
    ).toEqual(["instant-medium", "cached-small", "large", "medium"]);
  });

  it("can rank stream results by quality", () => {
    const source720 = streamFixture("720p", null, true, true, null, 20, "720p");
    const source4k = streamFixture("4k", null, true, true, null, 10, "4K");
    const source1080 = streamFixture("1080p", true, true, true, null, 30, "1080p");

    expect(
      sortStreamResults([source720, source4k, source1080], "quality").map((s) => s.title),
    ).toEqual(["1080p", "4k", "720p"]);
  });

  it("keeps cached streams first when ranking by size", () => {
    const smallCached = streamFixture("small-cached", true, true, true, null, 2, "4K");
    const largeUncached = streamFixture("large-uncached", null, true, true, null, 80, "720p");

    expect(sortStreamResults([smallCached, largeUncached], "size").map((s) => s.title)).toEqual([
      "small-cached",
      "large-uncached",
    ]);
  });

  it("recognizes provider-agnostic cached markers in stream titles", () => {
    const cachedTiny = streamFixture("[RD⚡] Cached release", null, true, true, null, 2, "1080p");
    const uncachedHuge = streamFixture("[PM⏳] Uncached release", null, true, true, null, 80, "4K");

    expect(sortStreamResults([uncachedHuge, cachedTiny], "size").map((s) => s.title)).toEqual([
      "[RD⚡] Cached release",
      "[PM⏳] Uncached release",
    ]);
  });
});

function requestPath(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function streamFixture(
  title: string,
  cached: boolean | null = null,
  hasUrl = true,
  hasInfoHash = true,
  providerLabel: string | null = null,
  sizeGiB: number | null = null,
  quality: string | null = null,
  seeders: number | null = null,
): StreamSearchResult {
  return {
    stream_key: title,
    title,
    season: null,
    episode: null,
    cached,
    has_url: hasUrl,
    has_info_hash: hasInfoHash,
    addable: hasInfoHash,
    selected: false,
    provider_label: providerLabel,
    seeders,
    parsed: {
      quality,
      codec: null,
      hdr: null,
      audio: null,
      size_bytes: sizeGiB === null ? null : sizeGiB * 1024 ** 3,
      size_label: sizeGiB === null ? null : `${String(sizeGiB)} GB`,
      source: null,
      language: null,
    },
  };
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
        debugLogging: true,
        seasonAutoCompleteEnabled: true,
        seasonAutoCompleteIntervalDays: "3",
        seasonAutoCompleteAllowUncached: true,
        seasonAutoCompleteShowsPerMinute: "2",
        torboxApiKey: "",
        tmdbApiKey: "tmdb",
        resolverToken: "",
        aiostreamsBaseUrl: " https://aio.example/manifest.json ",
        adminUsername: "",
        adminPassword: "",
      }),
    ).toEqual({
      base_url: "http://127.0.0.1:8001",
      movies_enabled: true,
      shows_enabled: false,
      anime_enabled: true,
      playback_mode: "direct",
      sync_interval_minutes: 120,
      debug_logging: true,
      season_auto_complete_enabled: true,
      season_auto_complete_interval_days: 3,
      season_auto_complete_allow_uncached: true,
      season_auto_complete_shows_per_minute: 2,
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
        debug_logging: true,
        season_auto_complete_enabled: true,
        season_auto_complete_interval_days: 3,
        season_auto_complete_allow_uncached: false,
        season_auto_complete_shows_per_minute: 2,
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
      debugLogging: true,
      seasonAutoCompleteEnabled: true,
      seasonAutoCompleteIntervalDays: "3",
      seasonAutoCompleteAllowUncached: false,
      seasonAutoCompleteShowsPerMinute: "2",
      torboxApiKey: "",
      tmdbApiKey: "",
      resolverToken: "",
      aiostreamsBaseUrl: "",
      adminUsername: "",
      adminPassword: "",
    });
  });

  it("formats setup missing fields", () => {
    expect(missingLabels(["base_url", "database_url", "torbox_api_key"])).toEqual(["TorBox key"]);
  });

  it("formats settings sources", () => {
    expect(settingSourceLabel("database")).toBe("Saved");
    expect(settingSourceLabel("environment")).toBe("Env");
    expect(settingSourceLabel(null)).toBe("Missing");
  });
});
