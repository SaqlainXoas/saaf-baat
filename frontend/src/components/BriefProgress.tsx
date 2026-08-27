/**
 * "4 / 12" plus a progress bar: the finiteness of the brief, made visible.
 *
 * The single most important thing this product says about itself is that it
 * ends. Mobile got this in Phase 5; desktop rendered twelve identical rows and
 * said nothing about how many were left, which is exactly the feed feeling the
 * product is defined against.
 */
export default function BriefProgress({
  position,
  total,
  variant = "sticky",
}: {
  position: number;
  total: number;
  variant?: "sticky" | "static";
}) {
  return (
    <>
      <div
        className={variant === "sticky" ? "sb-brief-progress sb-brief-progress-sticky" : "sb-brief-progress"}
        aria-hidden="true"
      >
        <span className="sb-brief-progress-count">
          {position} / {total}
        </span>
        <span className="sb-brief-progress-track">
          <span
            className="sb-brief-progress-fill"
            style={{ width: `${(position / Math.max(total, 1)) * 100}%` }}
          />
        </span>
      </div>
      <p className="sr-only" role="status">
        Story {position} of {total}
      </p>
    </>
  );
}
