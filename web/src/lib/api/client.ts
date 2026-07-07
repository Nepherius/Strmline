export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as T;
}

export async function fetchNoContent(path: string, init?: RequestInit): Promise<void> {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
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
