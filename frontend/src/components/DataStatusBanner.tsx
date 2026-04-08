import type { DataStatus } from "@/data/api";

export default function DataStatusBanner({
  status,
  message,
  latestCreatedAt,
  staleAfterHours = 6,
}: {
  status: DataStatus;
  message?: string;
  latestCreatedAt?: string;
  staleAfterHours?: number;
}) {
  const latestUpdate = parseLatestUpdate(latestCreatedAt);
  const staleFeed = status === "live" && latestUpdate ? latestUpdate.ageHours >= staleAfterHours : false;
  if (!staleFeed && (status === "live" || status === "not-found")) return null;
  const tone = status === "error-live-required" ? "error" : "warn";

  const body =
    staleFeed
      ? `This brief may be stale. Last successful live update: ${latestUpdate?.label}.`
      : message ||
        (status === "mock-no-api"
          ? "Showing the local preview brief because a live backend is not configured."
          : status === "error-live-required"
            ? "Live briefing is required, but the frontend cannot reach the backend API."
            : "Live briefing is unavailable right now. Showing the local preview brief instead.");

  const nonLiveSuffix = !staleFeed && latestUpdate ? ` Last successful live update: ${latestUpdate.label}.` : "";

  return (
    <div
      role="status"
      aria-live="polite"
      className="sb-status-banner"
      data-tone={tone}
    >
      {body}
      {nonLiveSuffix}
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
