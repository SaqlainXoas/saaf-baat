import Pill from "./primitives/Pill";
import Card from "./primitives/Card";
import type { StoryCardData } from "@/data/types";
import {
  capitalise,
  formatCategory,
  formatRelativeTime,
  getMetadataString,
} from "@/utils/storyMeta";

export default function StoryCard({
  story,
  isBackground = false,
  variant = "default",
}: {
  story: StoryCardData;
  isBackground?: boolean;
  variant?: "default" | "featured" | "compact" | "supporting";
}) {
  const primaryLabel = story.impact_labels?.[0] || "UPDATE";
  const sourceNames = story.sources.map((s) => capitalise(s.source));
  const isCompact = variant === "compact";
  const isFeatured = variant === "featured";
  const isSupporting = variant === "supporting";
  const isDefault = variant === "default";
  const whyItMatters = getMetadataString(story.metadata, "why_it_matters");
  const whatToWatch = getMetadataString(story.metadata, "what_to_watch");
  const updatedAt = formatRelativeTime(story.created_at);

  const headlineClass = isFeatured
    ? "sb-headline-featured"
    : isSupporting
      ? "sb-headline-supporting"
    : isCompact
      ? "sb-headline-compact"
      : "sb-headline-default";

  const snippetClass = isFeatured
    ? "sb-snippet-featured sb-clamp-2"
    : isSupporting
      ? "sb-snippet-supporting sb-clamp-2"
    : isCompact
      ? "sb-snippet-compact sb-clamp-2"
      : "sb-snippet-default sb-clamp-2";

  const featuredNote = whyItMatters || whatToWatch;
  const sourceSummary = sourceNames.join(" • ") || `${story.sources.length} source${story.sources.length === 1 ? "" : "s"}`;

  return (
    <Card
      interactive={!isBackground}
      className={isFeatured ? "p-4 md:p-5" : isSupporting ? "p-4 md:p-5" : isCompact ? "p-4" : "p-4"}
    >
      {isFeatured ? (
        <div>
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2 flex-wrap">
              <Pill label={primaryLabel} />
              <span className="sb-story-chip">
                {formatCategory(story.category)}
              </span>
            </div>
            {updatedAt ? (
              <span className="sb-meta flex-shrink-0">
                {updatedAt}
              </span>
            ) : null}
          </div>

          <h2 className={`${headlineClass} mt-3 sb-clamp-2`}>
            {story.headline}
          </h2>

          <p className={`${snippetClass} mt-2`}>
            {story.snippet}
          </p>

          {featuredNote ? (
            <p className="mt-3 text-sm leading-relaxed sb-clamp-2" style={{ color: "var(--ink-muted)" }}>
              {featuredNote}
            </p>
          ) : null}
        </div>
      ) : (
        <>
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2 flex-wrap">
              <Pill label={primaryLabel} />
              {!isCompact ? (
                <span className="sb-story-chip">
                  {formatCategory(story.category)}
                </span>
              ) : null}
            </div>
            {updatedAt ? (
              <span className="sb-meta flex-shrink-0">
                {updatedAt}
              </span>
            ) : null}
          </div>

          <h2 className={`${headlineClass} mt-3 sb-clamp-2`}>
            {story.headline}
          </h2>

          <p className={`${snippetClass} mt-2`}>
            {story.snippet}
          </p>

          {isDefault && featuredNote ? (
            <div className="mt-4 rounded-[22px] border px-4 py-3" style={{ borderColor: "var(--hairline)", background: "var(--surface-2)" }}>
              <p className="text-[11px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--ink-muted)" }}>
                {whatToWatch ? "What to watch" : "Why it matters"}
              </p>
              <p className="mt-2 text-sm leading-relaxed" style={{ color: "var(--ink)" }}>
                {whatToWatch || whyItMatters}
              </p>
            </div>
          ) : null}

        </>
      )}

      <div className="flex items-center justify-between mt-4">
        <span className="sb-meta">
          {isCompact || isSupporting ? sourceSummary : `Sources assessed: ${sourceSummary}`}
        </span>
        {!isBackground && (
          <span className="text-xs font-bold" style={{ color: "var(--teal)" }}>
            Open →
          </span>
        )}
      </div>
    </Card>
  );
}
