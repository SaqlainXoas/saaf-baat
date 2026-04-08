import Link from "next/link";
import { fetchStoryWithMeta } from "@/data/api";
import Pill from "@/components/primitives/Pill";
import Card from "@/components/primitives/Card";
import ConsensusEngine from "@/components/ConsensusEngine";
import OriginalSourcesList from "@/components/OriginalSourcesList";
import DataStatusBanner from "@/components/DataStatusBanner";
import SkipLink from "@/components/SkipLink";
import {
  capitalise,
  formatCategory,
  formatRelativeTime,
  getMetadataString,
} from "@/utils/storyMeta";

export default async function StoryDetail({
  params,
}: {
  params: Promise<{ cluster_id: string }>;
}) {
  const { cluster_id } = await params;
  const { story, status, message, latestPipelineRunAt } = await fetchStoryWithMeta(cluster_id);

  if (!story) {
    const isLiveModeError = status === "error-live-required";
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ background: "var(--paper)" }}
      >
        <div className="text-center p-8 max-w-sm">
          <p className="text-lg font-bold" style={{ color: "var(--ink)" }}>
            {isLiveModeError ? "Live story unavailable" : "Story unavailable"}
          </p>
          <p className="text-sm mt-2" style={{ color: "var(--ink-muted)" }}>
            {isLiveModeError
              ? (message || "The live story could not be loaded right now.")
              : "This story may have moved, expired, or not be available anymore."}
          </p>
          <Link
            href="/"
            className="inline-block mt-4 text-sm font-bold sb-focusable px-2 py-1 rounded-lg"
            style={{ color: "var(--teal)" }}
          >
            ← Back to brief
          </Link>
        </div>
      </div>
    );
  }

  const primaryLabel = story.impact_labels?.[0] || "UPDATE";
  const sourceNames = story.sources.map((s) => capitalise(s.source));
  const whyItMatters = getMetadataString(story.metadata, "why_it_matters");
  const whatToWatch = getMetadataString(story.metadata, "what_to_watch");
  const updatedAt = formatRelativeTime(story.created_at);
  const isSingleSource = story.sources.length <= 1;
  const sourceSupportLabel = isSingleSource ? "Single-source reporting" : "Multi-source reporting";
  const sourceSupportText = isSingleSource
    ? `Current reporting is still anchored to ${sourceNames[0] || "one publisher"} alone.`
    : `Source support in this brief: ${sourceNames.join(" • ")}.`;
  const topArticles = (story.articles || []).slice(0, 3);

  return (
    <div className="min-h-screen" style={{ background: "var(--paper)" }}>
      <div className="bg-ambient" />
      <SkipLink label="Skip to story" selector='[data-skip-target="story"]' />

      <main id="story-main" className="relative sb-container px-4 py-8" style={{ maxWidth: 980 }} role="main">
        <Link
          href="/"
          className="sb-focusable inline-flex items-center gap-1 text-sm px-2 py-1 rounded-lg"
          style={{ color: "var(--ink-muted)" }}
        >
          <span>←</span>
          <span>Back to brief</span>
        </Link>
        <div className="mt-3">
          <DataStatusBanner status={status} message={message} latestCreatedAt={latestPipelineRunAt} />
        </div>

        <div className="mt-4">
          <Card variant="flat" className="p-5 md:p-6">
            <div data-skip-target="story" tabIndex={-1}>
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex items-center gap-2 flex-wrap">
                  <Pill label={primaryLabel} />
                  <span className="sb-story-chip">
                    {formatCategory(story.category)}
                  </span>
                  <span className="sb-story-chip">
                    Quick brief
                  </span>
                </div>
                {updatedAt ? <span className="sb-meta">{updatedAt}</span> : null}
              </div>

              <h1 className="sb-headline-brief mt-3">
                <span className="block max-w-[18ch]">{story.headline}</span>
              </h1>

              <p className="sb-snippet-brief mt-3 max-w-3xl">
                {story.snippet}
              </p>

              <div className="flex gap-2 mt-4 flex-wrap">
                <span
                  className="text-xs px-2.5 py-1 rounded-full"
                  style={{
                    background: "color-mix(in srgb, var(--surface) 84%, var(--surface-base))",
                    border: "1px solid color-mix(in srgb, var(--outline-ghost) 72%, transparent)",
                    color: "var(--ink)",
                  }}
                >
                  {sourceSupportLabel}
                </span>
                {story.sources.map((s, i) => (
                  <span
                    key={i}
                    className="text-xs px-2.5 py-1 rounded-full"
                    style={{
                      background: "color-mix(in srgb, var(--surface-2) 84%, var(--surface-base))",
                      border: "1px solid color-mix(in srgb, var(--outline-ghost) 72%, transparent)",
                      color: "var(--ink)",
                    }}
                  >
                    {capitalise(s.source)}
                  </span>
                ))}
              </div>

              <p className="sb-meta mt-3">
                {sourceSupportText}
              </p>

              <div className="mt-5 grid gap-3 md:grid-cols-2">
                {whyItMatters ? (
                  <div className="sb-editorial-note">
                    <p className="text-xs font-bold uppercase tracking-[0.16em]" style={{ color: "var(--ink-muted)" }}>
                      Why it matters
                    </p>
                    <p className="text-sm mt-2 leading-relaxed" style={{ color: "var(--ink)" }}>
                      {whyItMatters}
                    </p>
                  </div>
                ) : null}
                {whatToWatch ? (
                  <div className="sb-editorial-note">
                    <p className="text-xs font-bold uppercase tracking-[0.16em]" style={{ color: "var(--ink-muted)" }}>
                      What to watch
                    </p>
                    <p className="text-sm mt-2 leading-relaxed" style={{ color: "var(--ink)" }}>
                      {whatToWatch}
                    </p>
                  </div>
                ) : null}
              </div>

              <div className="mt-4 sb-editorial-note">
                <p className="text-xs font-bold uppercase tracking-[0.16em]" style={{ color: "var(--ink-muted)" }}>
                  Top reporting
                </p>
                {topArticles.length ? (
                  <div className="mt-3 space-y-2">
                    {topArticles.map((article) => (
                      <a
                        key={article.id}
                        href={article.url}
                        target="_blank"
                        rel="noreferrer"
                        className="sb-focusable flex items-start justify-between gap-3 rounded-[16px] border px-3 py-2 transition-colors"
                        style={{
                          borderColor: "color-mix(in srgb, var(--outline-ghost) 72%, transparent)",
                          background: "color-mix(in srgb, var(--surface) 94%, var(--surface-base))",
                        }}
                      >
                        <span className="min-w-0">
                          <span className="block text-xs font-bold uppercase tracking-[0.16em]" style={{ color: "var(--teal)" }}>
                            {capitalise(article.source)}
                          </span>
                          <span className="mt-1 block text-sm leading-relaxed" style={{ color: "var(--ink)" }}>
                            {article.headline}
                          </span>
                        </span>
                        <span className="flex-shrink-0 text-xs font-bold" style={{ color: "var(--teal)" }}>
                          Read →
                        </span>
                      </a>
                    ))}
                  </div>
                ) : (
                  <p className="mt-2 text-sm leading-relaxed" style={{ color: "var(--ink-muted)" }}>
                    Original links are not available for this story yet.
                  </p>
                )}
              </div>
            </div>
          </Card>
        </div>

        <ConsensusEngine story={story} />

        <OriginalSourcesList articles={story.articles || []} />
      </main>
    </div>
  );
}
