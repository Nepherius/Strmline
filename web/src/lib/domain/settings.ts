export type SettingSource = "database" | "environment" | null;
export type PlaybackMode = "resolver" | "direct";

export interface AppSettings {
  base_url: string | null;
  library_root: string | null;
  movies_enabled: boolean;
  shows_enabled: boolean;
  anime_enabled: boolean;
  playback_mode: PlaybackMode;
  sync_interval_minutes: number;
  debug_logging: boolean;
  season_auto_complete_enabled: boolean;
  season_auto_complete_interval_days: number;
  season_auto_complete_allow_uncached: boolean;
  season_auto_complete_shows_per_minute: number;
  torbox_configured: boolean;
  tmdb_configured: boolean;
  resolver_configured: boolean;
  aiostreams_configured: boolean;
  base_url_source: SettingSource;
  library_root_source: SettingSource;
  torbox_source: SettingSource;
  tmdb_source: SettingSource;
  resolver_source: SettingSource;
  aiostreams_source: SettingSource;
}

export interface SetupStatus {
  configured: boolean;
  missing: string[];
}

export interface SettingsFormValues {
  baseUrl: string;
  moviesEnabled: boolean;
  showsEnabled: boolean;
  animeEnabled: boolean;
  playbackMode: PlaybackMode;
  syncIntervalMinutes: string;
  debugLogging: boolean;
  seasonAutoCompleteEnabled: boolean;
  seasonAutoCompleteIntervalDays: string;
  seasonAutoCompleteAllowUncached: boolean;
  seasonAutoCompleteShowsPerMinute: string;
  torboxApiKey: string;
  tmdbApiKey: string;
  resolverToken: string;
  aiostreamsBaseUrl: string;
  adminUsername: string;
  adminPassword: string;
}

export type SettingsPayload = Record<string, boolean | number | string>;

export function buildSettingsPayload(values: SettingsFormValues): SettingsPayload {
  const payload: SettingsPayload = {};
  setIfPresent(payload, "base_url", values.baseUrl);
  payload["movies_enabled"] = values.moviesEnabled;
  payload["shows_enabled"] = values.showsEnabled;
  payload["anime_enabled"] = values.animeEnabled;
  payload["playback_mode"] = values.playbackMode;
  setIntegerIfPresent(payload, "sync_interval_minutes", values.syncIntervalMinutes);
  payload["debug_logging"] = values.debugLogging;
  payload["season_auto_complete_enabled"] = values.seasonAutoCompleteEnabled;
  setIntegerIfPresent(
    payload,
    "season_auto_complete_interval_days",
    values.seasonAutoCompleteIntervalDays,
  );
  payload["season_auto_complete_allow_uncached"] = values.seasonAutoCompleteAllowUncached;
  setIntegerIfPresent(
    payload,
    "season_auto_complete_shows_per_minute",
    values.seasonAutoCompleteShowsPerMinute,
  );
  setIfPresent(payload, "torbox_api_key", values.torboxApiKey);
  setIfPresent(payload, "tmdb_api_key", values.tmdbApiKey);
  setIfPresent(payload, "resolver_token", values.resolverToken);
  setIfPresent(payload, "aiostreams_base_url", values.aiostreamsBaseUrl);
  return payload;
}

export function settingsToFormValues(settings: AppSettings | null): SettingsFormValues {
  return {
    baseUrl: settings?.base_url ?? "",
    moviesEnabled: settings?.movies_enabled ?? true,
    showsEnabled: settings?.shows_enabled ?? true,
    animeEnabled: settings?.anime_enabled ?? true,
    playbackMode: settings?.playback_mode ?? "resolver",
    syncIntervalMinutes: String(settings?.sync_interval_minutes ?? 360),
    debugLogging: settings?.debug_logging ?? false,
    seasonAutoCompleteEnabled: settings?.season_auto_complete_enabled ?? false,
    seasonAutoCompleteIntervalDays: String(settings?.season_auto_complete_interval_days ?? 1),
    seasonAutoCompleteAllowUncached: settings?.season_auto_complete_allow_uncached ?? false,
    seasonAutoCompleteShowsPerMinute: String(settings?.season_auto_complete_shows_per_minute ?? 1),
    torboxApiKey: "",
    tmdbApiKey: "",
    resolverToken: "",
    aiostreamsBaseUrl: "",
    adminUsername: "",
    adminPassword: "",
  };
}

export function missingLabels(missing: string[]): string[] {
  const labels: Record<string, string> = {
    sync_interval_minutes: "Sync interval",
    torbox_api_key: "TorBox key",
    admin_user: "Admin credentials",
  };
  return missing.flatMap((field) => (labels[field] ? [labels[field]] : []));
}

export function settingSourceLabel(source: SettingSource): string {
  if (source === "database") {
    return "Saved";
  }
  if (source === "environment") {
    return "Env";
  }
  return "Missing";
}

function setIfPresent(payload: SettingsPayload, key: string, value: string): void {
  const trimmed = value.trim();
  if (trimmed.length > 0) {
    payload[key] = trimmed;
  }
}

function setIntegerIfPresent(payload: SettingsPayload, key: string, value: string): void {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return;
  }
  const numericValue = Number(trimmed);
  if (Number.isInteger(numericValue)) {
    payload[key] = numericValue;
  }
}
