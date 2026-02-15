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

  const body =
    staleFeed
      ? `Feed may be stale. Last successful update: ${latestUpdate?.label}.`
      : message ||
        (status === "mock-no-api"
          ? "Showing local mock data. Set NEXT_PUBLIC_API_URL to load live stories."
          : status === "error-live-required"
            ? "Live data is required. Connect the frontend to a healthy backend API."
            : "Live backend is unavailable. Showing fallback data for now.");

  const nonLiveSuffix = !staleFeed && latestUpdate ? ` Last successful update: ${latestUpdate.label}.` : "";

  const isError = status === "error-live-required";

  return (
    <div
      role="status"
      className="rounded-2xl px-3 py-2 text-xs"
      style={{
        background: isError
          ? "color-mix(in srgb, #e85d4f 22%, var(--surface))"
          : "var(--amber-bg)",
        border: isError
          ? "1px solid color-mix(in srgb, #e85d4f 44%, var(--hairline))"
          : "1px solid color-mix(in srgb, var(--amber-bg) 56%, var(--hairline))",
        color: isError ? "var(--ink)" : "var(--ink)",
      }}
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
