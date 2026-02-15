import Link from "next/link";
import Pill from "./primitives/Pill";
import type { StoryCardData } from "@/data/types";

export default function StoryListItem({ story }: { story: StoryCardData }) {
  const primaryLabel = story.impact_labels?.[0] || "UPDATE";

  return (
    <Link
      href={`/stories/${story.story_id}`}
      className="sb-list-item sb-focusable block px-4 py-3"
    >
      <div className="flex items-center justify-between gap-3">
        <Pill label={primaryLabel} />
        <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
          Sources assessed: {story.sources.length}
        </span>
      </div>

      <h3
        className="text-sm font-bold mt-2 leading-tight tracking-tight"
        style={{
          color: "var(--ink)",
          display: "-webkit-box",
          WebkitBoxOrient: "vertical" as const,
          WebkitLineClamp: 2,
          overflow: "hidden",
        }}
      >
        {story.headline}
      </h3>

      {/* Trust chips row */}
      <div className="flex gap-1.5 mt-2 flex-wrap items-center">
        {story.confirmed_facts.slice(0, 2).map((e, i) => (
          <span
            key={`a-${i}`}
            className="text-xs px-2 py-0.5 rounded-full"
            style={{
              background: "var(--mint-bg)",
              border: "1px solid rgba(82, 183, 163, 0.2)",
            }}
          >
            {e.text}
          </span>
        ))}
        {story.debated_claims.slice(0, 1).map((e, i) => (
          <span
            key={`d-${i}`}
            className="text-xs px-2 py-0.5 rounded-full"
            style={{
              background: "var(--amber-bg)",
              border: "1px solid rgba(240, 195, 122, 0.35)",
            }}
          >
            {e.text}
          </span>
        ))}
      </div>
    </Link>
  );
}
