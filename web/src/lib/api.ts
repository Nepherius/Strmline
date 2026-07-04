export function normalizeApiBase(apiBase: string): string {
  return apiBase.trim().replace(/\/$/, "");
}

export async function fetchJson<T>(apiBase: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${normalizeApiBase(apiBase)}${path}`, init);
  if (!response.ok) {
    throw new Error(`API returned ${String(response.status)}`);
  }
  return (await response.json()) as T;
}
