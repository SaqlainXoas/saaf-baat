import Link from "next/link";
import { fetchStoryWithMeta } from "@/data/api";
import Pill from "@/components/primitives/Pill";
import OriginalSourcesList from "@/components/OriginalSourcesList";
import DataStatusBanner from "@/components/DataStatusBanner";
import SkipLink from "@/components/SkipLink";
import {
  publisherName,
  formatCategory,
  formatRelativeTime,
  latestReportTime,
  getMetadataString,
} from "@/utils/storyMeta";
import {
  publishersNamedInAnalysis,
  toAnalysisParagraphs,
} from "@/utils/analysisPresentation";

// Render each story once, then serve it from Vercel's cache and let the
// publish-time revalidate ping replace it. Without this a dynamic segment is
// re-rendered per request, so a reader opening a story hours after publication
// pays the Render Free cold start before anything appears. Nothing on this page
// reads cookies or headers, so there is nothing per-request to preserve.
export const dynamic = "force-static";
export const dynamicParams = true;
export const revalidate = 900;

export default async function StoryDetail({
  params,
}: {
  params: Promise<{ cluster_id: string }>;
}) {
  const { cluster_id } = await params;
  const { story, status, message, generatedAt, isFresh } = await fetchStoryWithMeta(cluster_id);

  // A failed backend fetch must throw, not render. This page is force-static,
  // so a rendered "unavailable" state is cached like a real story: one
  // transient 503 from a waking Render kept the brief's lead story on an error
  // page for every reader until the next revalidation. A throw is never cached
  // - Vercel keeps serving the last good render, and a first render falls
  // through to error.tsx and is retried on the next request.
  if (status === "error-live-required") {
    throw new Error(message || "The live story could not be loaded right now.");
  }

  if (!story) {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ background: "var(--paper)" }}
      >
        <div className="text-center p-8 max-w-sm">
          <p className="text-lg font-bold" style={{ color: "var(--ink)" }}>
            Story unavailable
          </p>
          <p className="text-sm mt-2" style={{ color: "var(--ink-muted)" }}>
            This story may have moved, expired, or not be available anymore.
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
  const sourceNames = story.sources.map((s) => publisherName(s.source));
  const whyItMatters = getMetadataString(story.metadata, "why_it_matters");
  const whatToWatch = getMetadataString(story.metadata, "what_to_watch");
  // The age of the newest original report, not of the pipeline row that
  // referenced it. Null when no source carries a timestamp we trust — the
  // chip is then omitted rather than filled with a number that means
  // something else.
  const latestReport = formatRelativeTime(latestReportTime(story.articles) || undefined);
  // "Analysis" is a claim about what the reader is looking at. When the
  // analysis is missing, what remains is one publisher's excerpt, and the
  // heading has to say so rather than dress it as the multi-source synthesis.
  const hasAnalysis = Boolean(story.analysis);
  const analysisBody = story.analysis || story.snippet;
  const analysisHeading = hasAnalysis ? "Analysis" : "From the reporting";
  const analysisParagraphs = hasAnalysis
    ? toAnalysisParagraphs(analysisBody)
    : [analysisBody];
  const analysisPublishers = publishersNamedInAnalysis(story.analysis);
  const analysisSources = story.analysis_sources || [];

  return (
    <div className="min-h-screen" style={{ background: "var(--paper)" }}>
      <div className="bg-ambient" />
      <SkipLink label="Skip to story" selector='[data-skip-target="story"]' />

      {/* A 920px reading column inside a 1220px shell left the page hugging the
          left edge with 300px of dead space beside it - the same imbalance the
          homepage had. The column is the right width for prose; it just needs
          to sit in the middle of the page. */}
      <main id="story-main" className="relative sb-container px-4 py-8" style={{ maxWidth: 780 }} role="main">
        <Link
          href="/"
          className="sb-focusable inline-flex max-w-full items-center gap-1 text-sm min-h-11 px-3 rounded-lg"
          style={{ color: "var(--ink-muted)" }}
        >
          <span>←</span>
          <span>Back to brief</span>
        </Link>
        <div className="mt-3">
          <div className="max-w-[920px]">
            <DataStatusBanner status={status} message={message} generatedAt={generatedAt} isFresh={isFresh} />
          </div>
        </div>

        <section className="mt-4 max-w-[920px]">
          <div data-skip-target="story" tabIndex={-1} className="min-w-0">
            <article className="sb-hero-shell p-5 md:p-7">
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex items-center gap-2 flex-wrap">
                  <Pill label={primaryLabel} />
                  <span className="sb-story-chip">{formatCategory(story.category)}</span>
                </div>
                {latestReport ? (
                  <span className="sb-meta">Latest report {latestReport}</span>
                ) : null}
              </div>

              <h1 className="sb-headline-brief mt-4 max-w-[26ch]">{story.headline}</h1>

              {sourceNames.length ? (
                <div className="mt-4 flex flex-wrap items-center gap-2" aria-label="Event sources">
                  {sourceNames.map((source) => (
                    <span key={source} className="sb-story-chip">{source}</span>
                  ))}
                </div>
              ) : null}

              {(whyItMatters || whatToWatch) ? (
                // Single column when only one note exists. `what_to_watch` is
                // optional now - it is written only when the reporting names a
                // real next event - so a fixed two-column grid left the lone
                // "Why it matters" box at half width beside 425px of nothing.
                <div
                  className={`mt-6 grid gap-3 ${
                    whyItMatters && whatToWatch ? "md:grid-cols-2" : "grid-cols-1"
                  }`}
                >
                  {whyItMatters ? (
                    <section className="sb-editorial-note" aria-labelledby="why-heading">
                      <h2 id="why-heading" className="text-xs font-bold uppercase tracking-[0.16em]" style={{ color: "var(--ink-muted)" }}>
                        Why it matters
                      </h2>
                      <p className="text-sm mt-2 leading-relaxed" style={{ color: "var(--ink)" }}>{whyItMatters}</p>
                    </section>
                  ) : null}
                  {whatToWatch ? (
                    <section className="sb-editorial-note" aria-labelledby="watch-heading">
                      <h2 id="watch-heading" className="text-xs font-bold uppercase tracking-[0.16em]" style={{ color: "var(--ink-muted)" }}>
                        What to watch
                      </h2>
                      <p className="text-sm mt-2 leading-relaxed" style={{ color: "var(--ink)" }}>{whatToWatch}</p>
                    </section>
                  ) : null}
                </div>
              ) : null}

              <section className="mt-7" aria-labelledby="analysis-heading">
                <h2 id="analysis-heading" className="sb-kicker">{analysisHeading}</h2>
                <div className="sb-analysis-copy mt-3">
                  {analysisParagraphs.map((paragraph, index) => (
                    <p key={index} className={index ? "mt-4" : undefined}>
                      {paragraph}
                    </p>
                  ))}
                </div>
                {!hasAnalysis ? (
                  <p className="sb-analysis-note mt-3">
                    A multi-source analysis is not available for this story. The
                    text above is an excerpt from one original report.
                  </p>
                ) : null}
              </section>

              {story.question ? (
                <section className="sb-question-callout mt-6" aria-labelledby="question-heading">
                  <h2 id="question-heading" className="sb-question-heading">The question</h2>
                  <p className="mt-3 text-base leading-relaxed" style={{ color: "var(--ink)" }}>
                    {story.question}
                  </p>
                </section>
              ) : null}


            </article>
          </div>
        </section>

        <div className="mt-8 max-w-[920px]">
          <OriginalSourcesList
            articles={story.articles || []}
            prioritiseSources={analysisPublishers}
          />
        </div>

        {analysisSources.length ? (
          <div className="mt-8 max-w-[920px]">
            <OriginalSourcesList
              articles={analysisSources}
              title="Related reporting used for analysis"
              description="Current reporting used for context. These reports are not counted as event corroboration."
              listId="analysis-sources-list"
              linkRole="context report"
            />
          </div>
        ) : null}
      </main>
    </div>
  );
}
