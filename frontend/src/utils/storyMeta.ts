import type { StoryArticleData, StoryMetadata } from "@/data/types";

export function publisherName(value: string) {
  const names: Record<string, string> = { dawn: "Dawn", tribune: "The Express Tribune", brecorder: "Business Recorder", geo: "Geo News", ary: "ARY News", thenews: "The News", nation: "The Nation", app: "Associated Press of Pakistan" };
  return names[value.toLowerCase()] || capitalise(value);
}

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

/**
 * When the newest original report behind a story was published.
 *
 * The detail page used to show `formatRelativeTime(story.created_at)`, which
 * is when the *pipeline wrote the row* — so a story whose newest source was
 * 13 hours old rendered "25m ago". A reader reads that as the age of the news.
 *
 * Returns null when no article carries a timestamp we trust. The caller must
 * render nothing in that case rather than falling back to `created_at`:
 * a pipeline write time relabelled as freshness is the UI asserting more than
 * the backend knows.
 */
export function latestReportTime(articles?: StoryArticleData[]): string | null {
  let newest: number | null = null;
  let newestIso: string | null = null;

  for (const article of articles || []) {
    // `missing` means the publisher gave us nothing datable; `date_only`
    // resolves to midnight, which would read as older than it is, so it is
    // only used when nothing precise exists.
    if (article.publish_date_status === "missing") continue;
    const raw =
      article.publish_date_status === "date_only"
        ? article.published_on || article.publish_date
        : article.publish_date;
    const value = Date.parse(raw || "");
    if (Number.isNaN(value)) continue;
    if (newest === null || value > newest) {
      newest = value;
      newestIso = raw || null;
    }
  }

  return newestIso;
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

/** An excerpt adds context only when it is prose, not a repeated title or image caption. */
export function cardSnippet(headline: string, snippet: string): string | null {
  const normalise = (text: string) => text.toLowerCase().replace(/[^a-z0-9]/g, "");
  if (!snippet.trim() || normalise(headline) === normalise(snippet)) return null;
  if (/^(?:this |a )?(?:photo|photograph|collage|image|picture) (?:shows|showing)\b/i.test(snippet.trim())) return null;
  return snippet;
}
