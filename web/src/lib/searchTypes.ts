import type { ParsedStreamResponse } from "./searchApi";

export function getQualityBadgeClass(quality: string | null): string {
  if (!quality) return "badge-gray";
  const q = quality.toLowerCase();
  if (q === "4k") return "badge-purple";
  if (q === "1080p") return "badge-blue";
  if (q === "720p") return "badge-green";
  if (q === "480p" || q === "360p") return "badge-yellow";
  if (["cam", "ts", "scr"].includes(q)) return "badge-red";
  return "badge-gray";
}

export function formatCodecAndHdr(parsed: ParsedStreamResponse): string {
  const parts: string[] = [];
  if (parsed.codec) parts.push(parsed.codec);
  if (parsed.hdr) parts.push(parsed.hdr);
  if (parsed.source) parts.push(parsed.source);
  return parts.length > 0 ? parts.join(" · ") : "Unknown codec/source";
}

export function formatAudio(parsed: ParsedStreamResponse): string {
  return parsed.audio ?? "Stereo/Unknown";
}

export function formatLanguage(parsed: ParsedStreamResponse): string {
  return parsed.language ?? "Unknown lang";
}
