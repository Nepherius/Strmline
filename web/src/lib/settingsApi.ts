import { fetchJson } from "$lib/api";
import {
  buildSettingsPayload,
  type AppSettings,
  type SettingsFormValues,
  type SetupStatus,
} from "$lib/settings";

export function loadSettings(apiBase: string): Promise<AppSettings> {
  return fetchJson<AppSettings>(apiBase, "/api/settings");
}

export function loadSetupStatus(apiBase: string): Promise<SetupStatus> {
  return fetchJson<SetupStatus>(apiBase, "/api/setup/status");
}

export function saveSettings(apiBase: string, values: SettingsFormValues): Promise<AppSettings> {
  return fetchJson<AppSettings>(apiBase, "/api/settings", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(buildSettingsPayload(values)),
  });
}

export function clearSavedSettings(apiBase: string): Promise<AppSettings> {
  return fetchJson<AppSettings>(apiBase, "/api/settings", {
    method: "DELETE",
  });
}
