export function normalizeApiBase(apiBase: string): string {
  return apiBase.trim().replace(/\/$/, "");
}

export async function fetchJson<T>(apiBase: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${normalizeApiBase(apiBase)}${path}`, init);
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as T;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string" && payload.detail.trim().length > 0) {
      return payload.detail;
    }
  } catch {
    // Fall back to status text below for non-JSON errors.
  }
  return `API returned ${String(response.status)}`;
}
