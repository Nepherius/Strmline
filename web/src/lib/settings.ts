export type SettingSource = "database" | "environment" | null;

export interface AppSettings {
  base_url: string | null;
  library_root: string | null;
  movies_enabled: boolean;
  shows_enabled: boolean;
  anime_enabled: boolean;
  torbox_configured: boolean;
  tmdb_configured: boolean;
  resolver_configured: boolean;
  base_url_source: SettingSource;
  library_root_source: SettingSource;
  torbox_source: SettingSource;
  tmdb_source: SettingSource;
  resolver_source: SettingSource;
}

export interface SetupStatus {
  configured: boolean;
  missing: string[];
}

export interface SettingsFormValues {
  baseUrl: string;
  libraryRoot: string;
  moviesEnabled: boolean;
  showsEnabled: boolean;
  animeEnabled: boolean;
  torboxApiKey: string;
  tmdbApiKey: string;
  resolverToken: string;
}

export type SettingsPayload = Record<string, boolean | string>;

export function buildSettingsPayload(values: SettingsFormValues): SettingsPayload {
  const payload: SettingsPayload = {};
  setIfPresent(payload, "base_url", values.baseUrl);
  setIfPresent(payload, "library_root", values.libraryRoot);
  payload["movies_enabled"] = values.moviesEnabled;
  payload["shows_enabled"] = values.showsEnabled;
  payload["anime_enabled"] = values.animeEnabled;
  setIfPresent(payload, "torbox_api_key", values.torboxApiKey);
  setIfPresent(payload, "tmdb_api_key", values.tmdbApiKey);
  setIfPresent(payload, "resolver_token", values.resolverToken);
  return payload;
}

export function settingsToFormValues(settings: AppSettings | null): SettingsFormValues {
  return {
    baseUrl: settings?.base_url ?? "",
    libraryRoot: settings?.library_root ?? "",
    moviesEnabled: settings?.movies_enabled ?? true,
    showsEnabled: settings?.shows_enabled ?? true,
    animeEnabled: settings?.anime_enabled ?? true,
    torboxApiKey: "",
    tmdbApiKey: "",
    resolverToken: "",
  };
}

export function missingLabels(missing: string[]): string[] {
  const labels: Record<string, string> = {
    base_url: "Base URL",
    database_url: "Database",
    library_root: "Library root",
    resolver_token: "Resolver token",
    tmdb_api_key: "TMDB key",
    torbox_api_key: "TorBox key",
  };
  return missing.map((field) => labels[field] ?? field);
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
