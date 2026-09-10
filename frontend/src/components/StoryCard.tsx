import Pill from "./primitives/Pill";
import Card from "./primitives/Card";
import type { StoryCardData } from "@/data/types";
import { publisherName, getMetadataString, cardSnippet } from "@/utils/storyMeta";

/**
 * One card of the brief, in the one shape both surfaces use.
 *
 * There used to be five variants. Two of them (`default`, `compact`) were
 * reachable from no caller and were kept alive only by their own tests, and a
 * third (`homepage`) existed purely because desktop rendered rows instead of
 * cards. What is left is the distinction that means something to a reader:
 * the story the day leads with, and the ones after it.
 *
 * The reading order is deliberate and identical in both:
 *   label -> headline -> why it matters -> what happened -> what to watch
 * `why_it_matters` sits directly under the headline at full ink weight because
 * it is the line the product exists to deliver. For a long time it was written
 * into metadata and rendered nowhere a reader could see it.
 */
export default function StoryCard({
  story,
  isBackground = false,
  variant = "supporting",
}: {
  story: StoryCardData;
  isBackground?: boolean;
  variant?: "lead" | "supporting";
}) {
  const snippet = cardSnippet(story.headline, story.snippet);
  const isLead = variant === "lead";
  const primaryLabel = story.impact_labels?.[0] || "UPDATE";
  const sourceNames = story.sources.map((s) => publisherName(s.source));
  const whyItMatters = getMetadataString(story.metadata, "why_it_matters");
  const whatToWatch = getMetadataString(story.metadata, "what_to_watch");
  const sourceChipLabel =
    story.sources.length <= 1
      ? sourceNames[0] || "Single source"
      : story.sources.length <= 3
        ? sourceNames.join(" · ")
        : `${story.sources.length} sources`;

  return (
    <Card
      interactive={!isBackground}
      padded={false}
      className={`sb-story-card ${isLead ? "sb-story-card-lead" : "sb-story-card-supporting"}`}
    >
      <div className="flex h-full flex-col">
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <Pill label={primaryLabel} />
          </div>

          <h2 className={`${isLead ? "sb-headline-lead" : "sb-headline-supporting"}`}>
            {story.headline}
          </h2>

          {whyItMatters ? <div className="sb-card-impact"><span className="sb-kicker">Why it matters</span><p className="sb-impact-line">{whyItMatters}</p></div> : null}

          {snippet ? <p className={`${isLead ? "sb-snippet-lead" : "sb-snippet-supporting"} sb-clamp-2`}>
            {snippet}
          </p> : null}

          {whatToWatch ? (
            <p className="sb-meta sb-watch-line">
              <span className="sb-watch-label">What to watch:</span> {whatToWatch}
            </p>
          ) : null}
        </div>

        <div className="sb-story-card-foot">
          <span className="sb-meta" style={{ opacity: story.sources.length <= 1 ? 0.72 : 1 }}>
            {sourceChipLabel}
          </span>
          {!isBackground ? <span className="sb-open-link">Read brief →</span> : null}
        </div>
      </div>
    </Card>
  );
}
