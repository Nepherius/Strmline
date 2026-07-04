export type SettingSource = "database" | "environment" | null;

export interface AppSettings {
  base_url: string | null;
  library_root: string | null;
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
  torboxApiKey: string;
  tmdbApiKey: string;
  resolverToken: string;
}

export function buildSettingsPayload(values: SettingsFormValues): Record<string, string> {
  const payload: Record<string, string> = {};
  setIfPresent(payload, "base_url", values.baseUrl);
  setIfPresent(payload, "library_root", values.libraryRoot);
  setIfPresent(payload, "torbox_api_key", values.torboxApiKey);
  setIfPresent(payload, "tmdb_api_key", values.tmdbApiKey);
  setIfPresent(payload, "resolver_token", values.resolverToken);
  return payload;
}

export function settingsToFormValues(settings: AppSettings | null): SettingsFormValues {
  return {
    baseUrl: settings?.base_url ?? "",
    libraryRoot: settings?.library_root ?? "",
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

function setIfPresent(payload: Record<string, string>, key: string, value: string): void {
  const trimmed = value.trim();
  if (trimmed.length > 0) {
    payload[key] = trimmed;
  }
}
