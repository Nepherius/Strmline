import { fetchJson } from "$lib/api/client";
import {
  buildSettingsPayload,
  type AppSettings,
  type SettingsFormValues,
} from "$lib/domain/settings";

export function loadSettings(): Promise<AppSettings> {
  return fetchJson<AppSettings>("/api/settings");
}

export function saveSettings(values: SettingsFormValues): Promise<AppSettings> {
  return fetchJson<AppSettings>("/api/settings", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(buildSettingsPayload(values)),
  });
}

export function clearSavedSettings(): Promise<AppSettings> {
  return fetchJson<AppSettings>("/api/settings", {
    method: "DELETE",
  });
}
