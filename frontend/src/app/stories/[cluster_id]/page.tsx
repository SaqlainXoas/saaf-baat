import Link from "next/link";
import { fetchStoryWithMeta } from "@/data/api";
import Pill from "@/components/primitives/Pill";
import Card from "@/components/primitives/Card";
import ConsensusEngine from "@/components/ConsensusEngine";
import OriginalSourcesList from "@/components/OriginalSourcesList";
import DataStatusBanner from "@/components/DataStatusBanner";

function capitalise(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default async function StoryDetail({
  params,
}: {
  params: Promise<{ cluster_id: string }>;
}) {
  const { cluster_id } = await params;
  const { story, status } = await fetchStoryWithMeta(cluster_id);

  if (!story) {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ background: "var(--paper)" }}
      >
        <div className="text-center p-8 max-w-sm">
          <p className="text-lg font-bold" style={{ color: "var(--ink)" }}>
            Story not found
          </p>
          <p className="text-sm mt-2" style={{ color: "var(--ink-muted)" }}>
            This story may have been updated or removed.
          </p>
          <Link
            href="/"
            className="inline-block mt-4 text-sm font-bold"
            style={{ color: "var(--teal)" }}
          >
            ← Back to brief
          </Link>
        </div>
      </div>
    );
  }

  const primaryLabel = story.impact_labels?.[0] || "UPDATE";
  const sourceCount = story.articles?.length || story.sources?.length || 0;
  const sourceNames = story.sources.map((s) => capitalise(s.source));

  return (
    <div className="min-h-screen" style={{ background: "var(--paper)" }}>
      <div className="bg-ambient" />

      <div className="relative sb-container px-4 py-6">
        <Link
          href="/"
          className="sb-focusable inline-flex items-center gap-1 text-sm px-2 py-1 rounded-lg"
          style={{ color: "var(--ink-muted)" }}
        >
          <span>←</span>
          <span>Back to brief</span>
        </Link>
        <div className="mt-3">
          <DataStatusBanner status={status} />
        </div>

        <div className="mt-4">
          <Card variant="flat">
            <Pill label={primaryLabel} />

            <h1 className="sb-headline-detail mt-3">
              {story.headline}
            </h1>

            <p className="sb-snippet-detail mt-3">
              {story.snippet}
            </p>

            <div className="flex gap-2 mt-3 flex-wrap">
              {story.sources.map((s, i) => (
                <span
                  key={i}
                  className="text-xs px-2.5 py-1 rounded-full"
                  style={{
                    background: "var(--surface-2)",
                    border: "1px solid var(--hairline)",
                    color: "var(--ink)",
                  }}
                >
                  {capitalise(s.source)}
                </span>
              ))}
            </div>

            <p className="sb-meta mt-2">
              Sources assessed: {sourceNames.join(" • ")}
            </p>
          </Card>
        </div>

        <ConsensusEngine
          confirmedFacts={story.confirmed_facts || []}
          debatedClaims={story.debated_claims || []}
          sourceCount={sourceCount}
        />

        <OriginalSourcesList articles={story.articles || []} />
      </div>
    </div>
  );
}
