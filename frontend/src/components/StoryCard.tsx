import Pill from "./primitives/Pill";
import Card from "./primitives/Card";
import TrustPreview from "./TrustPreview";
import type { StoryCardData } from "@/data/types";

function capitalise(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default function StoryCard({
  story,
  isBackground = false,
  variant = "default",
}: {
  story: StoryCardData;
  isBackground?: boolean;
  variant?: "default" | "featured" | "compact";
}) {
  const primaryLabel = story.impact_labels?.[0] || "UPDATE";
  const sourceNames = story.sources.map((s) => capitalise(s.source));
  const isCompact = variant === "compact";
  const isFeatured = variant === "featured";

  const headlineClass = isFeatured
    ? "sb-headline-featured"
    : isCompact
      ? "sb-headline-compact"
      : "sb-headline-default";

  const snippetClass = isFeatured
    ? "sb-snippet-featured sb-clamp-2"
    : isCompact
      ? "sb-snippet-compact sb-clamp-1"
      : "sb-snippet-default sb-clamp-2";

  return (
    <Card
      interactive={!isBackground}
      className={isFeatured ? "p-5" : isCompact ? "p-3.5" : "p-4"}
    >
      <Pill label={primaryLabel} />

      <h2 className={`${headlineClass} mt-3 sb-clamp-2`}>
        {story.headline}
      </h2>

      <p className={`${snippetClass} mt-2`}>
        {story.snippet}
      </p>

      <TrustPreview
        confirmedFacts={story.confirmed_facts}
        debatedClaims={story.debated_claims}
        layout={isCompact ? "compact" : "default"}
      />

      <div className="flex items-center justify-between mt-3">
        <span className="sb-meta">
          {isCompact
            ? `Sources assessed: ${story.sources.length}`
            : `Sources assessed: ${sourceNames.join(" • ")}`}
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
