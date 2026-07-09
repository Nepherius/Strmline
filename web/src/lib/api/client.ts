import { goto } from "$app/navigation";
import { browser } from "$app/environment";
import { resolve } from "$app/paths";

function buildInit(init?: RequestInit): RequestInit {
  const requestInit = init ?? {};
  const headers = new Headers(requestInit.headers);
  headers.set("X-Requested-With", "XMLHttpRequest");
  
  return {
    ...requestInit,
    headers,
    credentials: "same-origin",
  };
}

function handleResponse(response: Response): void {
  if (response.status === 401 && browser) {
    const pathname = window.location.pathname;
    if (pathname !== resolve("/login") && pathname !== resolve("/setup")) {
      void goto(resolve("/login"));
    }
  }
}


export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const finalInit = buildInit(init);
  const response = await fetch(path, finalInit);
  handleResponse(response);
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as T;
}

export async function fetchNoContent(path: string, init?: RequestInit): Promise<void> {
  const finalInit = buildInit(init);
  const response = await fetch(path, finalInit);
  handleResponse(response);
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

