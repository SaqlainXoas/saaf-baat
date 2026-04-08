import type { StoryCardData } from "@/data/types";
import { buildConsensusSummary } from "@/utils/storyPresentation";

export default function TrustPreview({
  story,
  layout = "default",
}: {
  story: StoryCardData;
  layout?: "default" | "compact";
}) {
  const summary = buildConsensusSummary(story);
  const agreed = summary.agreed.slice(0, layout === "compact" ? 1 : 2);
  const debated = summary.debated.slice(0, 1);
  const isSingleSource = story.sources.length <= 1;
  const agreedLabel = isSingleSource ? "What’s clear in current reporting" : "Where reporting lines up";
  const debatedLabel = "What to watch";

  if (layout === "compact") {
    return (
      <div className="mt-3 space-y-1.5">
        {agreed[0] ? (
          <p className="text-xs leading-relaxed" style={{ color: "var(--ink-muted)" }}>
            <span className="font-semibold" style={{ color: "var(--ink)" }}>
              Clear:
            </span>{" "}
            {agreed[0]}
          </p>
        ) : null}
        {debated[0] ? (
          <p className="text-xs leading-relaxed" style={{ color: "var(--ink-muted)" }}>
            <span className="font-semibold" style={{ color: "var(--ink)" }}>
              Watch:
            </span>{" "}
            {debated[0]}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
      <div className="sb-summary-panel sb-summary-panel-agreed">
        <p className="sb-summary-label">{agreedLabel}</p>
        <ul className="mt-3 space-y-2">
          {agreed.map((item) => (
            <li key={item} className="sb-summary-item">
              <span className="sb-summary-bullet">✓</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="sb-summary-panel sb-summary-panel-debated">
        <p className="sb-summary-label">{debatedLabel}</p>
        <ul className="mt-3 space-y-2">
          {debated.map((item) => (
            <li key={item} className="sb-summary-item">
              <span className="sb-summary-bullet">?</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
