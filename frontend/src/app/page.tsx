import { fetchFeedWithMeta } from "@/data/api";
import MorningGreeting from "@/components/MorningGreeting";
import DesktopBrief from "@/components/DesktopBrief";
import Deck from "@/components/Deck";
import Link from "next/link";
import { applyFilters, deriveAvailableSources, parseFilters } from "@/utils/focusFilters";
import DataStatusBanner from "@/components/DataStatusBanner";
import SkipLink from "@/components/SkipLink";

const MAX_STORIES = 9;

function hasRenderableImpactLine(story: { metadata?: { why_it_matters?: unknown } }) {
  const value = story.metadata?.why_it_matters;
  return typeof value === "string" && value.trim().length > 0;
}

function toURLSearchParams(searchParams?: Record<string, string | string[] | undefined>) {
  const params = new URLSearchParams();
  if (!searchParams) return params;
  for (const [key, value] of Object.entries(searchParams)) {
    if (Array.isArray(value)) value.forEach((v) => params.append(key, v));
    else if (typeof value === "string") params.set(key, value);
  }
  return params;
}

export default async function Home({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const resolvedSearchParams = searchParams ? await searchParams : undefined;
  const feedResult = await fetchFeedWithMeta();
  const allStories = feedResult.stories.filter(hasRenderableImpactLine);
  const availableSources = deriveAvailableSources(allStories);
  const urlParams = toURLSearchParams(resolvedSearchParams);
  const filters = parseFilters(urlParams);
  const filtered = applyFilters(allStories, filters);
  const stories = filtered.slice(0, MAX_STORIES);
  const generatedAt = feedResult.generatedAt;
  const hasFilters = urlParams.has("impact") || urlParams.has("sources");
  const hasLiveDataError = feedResult.status === "error-live-required";

  return (
    <div className="min-h-screen" style={{ background: "var(--paper)" }}>
      <div className="bg-ambient" />
      <SkipLink label="Skip to stories" selector='[data-skip-target="stories"]' />

      <main id="main-content" className="relative" role="main">
        {/* ── Desktop: single-flow brief (feed) ── */}
        <div className="hidden lg:block">
          {hasLiveDataError ? (
            <div className="sb-container px-4 py-2" style={{ maxWidth: 900 }}>
              <LiveDataErrorState message={feedResult.message} />
            </div>
          ) : stories.length > 0 ? (
            <DesktopBrief
              stories={stories}
              availableSources={availableSources}
              status={feedResult.status}
              statusMessage={feedResult.message}
              generatedAt={generatedAt}
              isFresh={feedResult.isFresh}
            />
          ) : (
            <div className="sb-container px-4 py-2" style={{ maxWidth: 900 }}>
              <EmptyState hasFilters={hasFilters} />
            </div>
          )}
        </div>

        {/* ── Mobile: greeting + card deck ── */}
        <div className="lg:hidden max-w-md mx-auto px-4">
          <MorningGreeting storyCount={stories.length} availableSources={availableSources} generatedAt={generatedAt} />
          <DataStatusBanner
            status={feedResult.status}
            message={feedResult.message}
            generatedAt={generatedAt}
            isFresh={feedResult.isFresh}
            storyCount={stories.length}
          />

          {hasLiveDataError ? (
            <LiveDataErrorState compact message={feedResult.message} />
          ) : stories.length > 0 ? (
            <div className="mt-3">
              <Deck stories={stories} />
            </div>
          ) : (
            <EmptyState hasFilters={hasFilters} />
          )}
        </div>
      </main>
    </div>
  );
}

function LiveDataErrorState({ message, compact = false }: { message?: string; compact?: boolean }) {
  return (
    <div className={`text-center ${compact ? "py-10" : "py-20"} px-6`}>
      <p className="text-lg font-bold" style={{ color: "var(--ink)" }}>
        Unable to load brief
      </p>
      <p className="text-sm mt-2" style={{ color: "var(--ink-muted)" }}>
        {message || "Please try again shortly."}
      </p>
      <Link
        href="/"
        className="inline-block mt-4 text-sm font-bold sb-focusable px-4 py-2 rounded-xl"
        style={{ background: "var(--surface)", border: "1px solid var(--hairline)", color: "var(--ink)" }}
      >
        Retry
      </Link>
    </div>
  );
}

function EmptyState({ hasFilters }: { hasFilters: boolean }) {
  return (
    <div className="text-center py-20 px-6">
      <p className="text-lg font-bold" style={{ color: "var(--ink)" }}>
        {hasFilters ? "No stories match this focus" : "Today's brief is being prepared"}
      </p>
      <p className="text-sm mt-2" style={{ color: "var(--ink-muted)" }}>
        {hasFilters
          ? "Try a broader focus to see the full brief."
          : "Check back after 7am PKT."}
      </p>
      {hasFilters ? (
        <Link
          href="/"
          className="inline-block mt-4 text-sm font-bold sb-focusable px-4 py-2 rounded-xl"
          style={{ background: "var(--surface)", border: "1px solid var(--hairline)", color: "var(--ink)" }}
        >
          Clear focus
        </Link>
      ) : null}
    </div>
  );
}
