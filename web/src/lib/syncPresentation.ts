export type SyncStatusVariant = "default" | "warn" | "ready";

export function syncStatusLabel(status: string): string {
  if (status === "success") return "Success";
  if (status === "failed") return "Failed";
  return status || "Unknown";
}

export function syncStatusVariant(status: string): SyncStatusVariant {
  if (status === "success") return "ready";
  if (status === "failed") return "warn";
  return "default";
}
