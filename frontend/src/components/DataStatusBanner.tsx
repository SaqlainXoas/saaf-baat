import type { DataStatus } from "@/data/api";

export default function DataStatusBanner({
  status,
  message,
  generatedAt,
  isFresh,
  storyCount,
}: {
  status: DataStatus;
  message?: string;
  generatedAt?: string;
  isFresh?: boolean;
  storyCount?: number;
}) {
  if (status === "not-found") return null;

  const latestUpdate = parseLatestUpdate(generatedAt);
  const staleFeed = status === "live" && storyCount !== 0 && isFresh === false;
  const partialBrief = status === "live" && typeof storyCount === "number" && storyCount > 0 && storyCount < 5;
  const emptyBrief = status === "live" && storyCount === 0;
  if (!staleFeed && !partialBrief && !emptyBrief && status === "live") return null;
  const tone = status === "error-live-required" ? "error" : "warn";

  const body =
    emptyBrief
      ? "Today's brief is being prepared. Check back after 7am PKT."
      : partialBrief
        ? "Partial brief — more stories being reviewed"
        : staleFeed
      ? "Brief not updated yet today. Showing last available brief."
      : message ||
        (status === "mock-no-api"
          ? "Showing the local preview brief because a live backend is not configured."
          : status === "error-live-required"
            ? "Unable to load brief. Please try again shortly."
            : "Live briefing is unavailable right now. Showing the local preview brief instead.");

  const suffix =
    latestUpdate && (staleFeed || status !== "live")
      ? ` Last successful live update: ${latestUpdate.label}.`
      : "";

  return (
    <div
      role="status"
      aria-live="polite"
      className="sb-status-banner"
      data-tone={tone}
    >
      {body}
      {suffix}
    </div>
  );
}

function parseLatestUpdate(timestamp?: string) {
  if (!timestamp) return null;
  const time = new Date(timestamp).getTime();
  if (Number.isNaN(time)) return null;

  const ageMs = Math.max(0, Date.now() - time);
  const ageHours = ageMs / 3_600_000;
  const ageMinutes = ageMs / 60_000;

  if (ageMinutes < 1) return { ageHours, label: "just now" };
  if (ageMinutes < 60) return { ageHours, label: `${Math.floor(ageMinutes)}m ago` };
  if (ageHours < 24) return { ageHours, label: `${Math.floor(ageHours)}h ago` };
  return { ageHours, label: `${Math.floor(ageHours / 24)}d ago` };
}
