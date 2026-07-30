export interface MediaFile {
  key: string;
  name: string;
  path: string;
  size: number | null;
  mime_type: string | null;
  season: number | null;
  episode: number | null;
  version_count: number;
}

export interface MediaFileManifest {
  ok: boolean;
  available: boolean;
  message: string;
  total_files: number;
  displayed_files: number;
  source_count: number;
  files: MediaFile[];
}

export function formatFileSize(size: number | null): string {
  if (size === null) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = size;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const precision = value >= 10 || unitIndex === 0 ? 0 : 1;
  return `${value.toFixed(precision)} ${units[unitIndex] ?? "B"}`;
}

export function episodeLabel(file: MediaFile): string | null {
  if (file.season === null || file.episode === null) return null;
  return `S${String(file.season).padStart(2, "0")}E${String(file.episode).padStart(2, "0")}`;
}
