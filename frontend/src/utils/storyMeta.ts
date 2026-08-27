import type { StoryMetadata } from "@/data/types";

export function capitalise(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function formatCategory(category: string) {
  return category
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map(capitalise)
    .join(" ");
}

export function getMetadataString(
  metadata: StoryMetadata | undefined,
  key: keyof StoryMetadata,
): string | null {
  const raw = metadata?.[key];
  if (typeof raw !== "string") return null;
  const trimmed = raw.trim();
  return trimmed ? trimmed : null;
}

export function formatRelativeTime(timestamp?: string) {
  if (!timestamp) return null;
  const value = Date.parse(timestamp);
  if (Number.isNaN(value)) return null;

  const diffMs = Date.now() - value;
  const diffMinutes = Math.max(0, Math.round(diffMs / 60_000));
  if (diffMinutes < 1) return "Just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;

  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  const diffDays = Math.round(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;

  return new Intl.DateTimeFormat("en-PK", {
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

export function formatSourceTimestamp(timestamp?: string) {
  if (!timestamp) return null;
  const value = Date.parse(timestamp);
  if (Number.isNaN(value)) return null;

  const date = new Date(value);
  const now = new Date();
  const includeYear = date.getUTCFullYear() !== now.getUTCFullYear();

  const dateLabel = new Intl.DateTimeFormat("en-PK", {
    month: "short",
    day: "numeric",
    ...(includeYear ? { year: "numeric" as const } : {}),
    timeZone: "Asia/Karachi",
  }).format(date);

  const timeLabel = new Intl.DateTimeFormat("en-PK", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone: "Asia/Karachi",
  }).format(date);

  return `${dateLabel}, ${timeLabel} PKT`;
}

export function formatSourceDate(dateInput?: string) {
  if (!dateInput) return null;
  const value = Date.parse(dateInput);
  if (Number.isNaN(value)) return null;

  const date = new Date(value);
  const now = new Date();
  const includeYear = date.getUTCFullYear() !== now.getUTCFullYear();

  return new Intl.DateTimeFormat("en-PK", {
    month: "short",
    day: "numeric",
    ...(includeYear ? { year: "numeric" as const } : {}),
    timeZone: "Asia/Karachi",
  }).format(date);
}
