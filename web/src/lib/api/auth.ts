import { fetchJson, fetchNoContent } from "$lib/api/client";

export interface UserProfile {
  id: number;
  username: string;
}

export function login(username: string, password: string): Promise<UserProfile> {
  return fetchJson<UserProfile>("/api/auth/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ username, password }),
  });
}

export function setupAdminUser(username: string, password: string): Promise<UserProfile> {
  return fetchJson<UserProfile>("/api/auth/setup", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ username, password }),
  });
}

export function logout(): Promise<void> {
  return fetchNoContent("/api/auth/logout", {
    method: "POST",
  });
}

export function loadMe(): Promise<UserProfile> {
  return fetchJson<UserProfile>("/api/auth/me");
}
