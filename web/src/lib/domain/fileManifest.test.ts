import { describe, expect, it } from "vitest";

import { episodeLabel, formatFileSize, type MediaFile } from "./fileManifest";

const episode: MediaFile = {
  key: "episode:1:2",
  name: "Show.S01E02.mkv",
  path: "Season 01/Show.S01E02.mkv",
  size: 1_610_612_736,
  mime_type: "video/x-matroska",
  season: 1,
  episode: 2,
  version_count: 2,
};

describe("file manifest presentation", () => {
  it("formats episode identities", () => {
    expect(episodeLabel(episode)).toBe("S01E02");
  });

  it("formats binary file sizes", () => {
    expect(formatFileSize(episode.size)).toBe("1.5 GB");
    expect(formatFileSize(null)).toBe("");
  });
});
