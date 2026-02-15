import type { DataStatus } from "@/data/api";

export default function DataStatusBanner({
  status,
}: {
  status: DataStatus;
}) {
  if (status === "live" || status === "not-found") return null;

  const message =
    status === "mock-no-api"
      ? "Showing local mock data. Set NEXT_PUBLIC_API_URL to load live stories."
      : "Live backend is unavailable. Showing fallback data for now.";

  return (
    <div
      role="status"
      className="rounded-2xl px-3 py-2 text-xs"
      style={{
        background: "var(--amber-bg)",
        border: "1px solid color-mix(in srgb, var(--amber-bg) 56%, var(--hairline))",
        color: "var(--ink-muted)",
      }}
    >
      {message}
    </div>
  );
}
