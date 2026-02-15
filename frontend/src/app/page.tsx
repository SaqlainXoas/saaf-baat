import { fetchFeedWithMeta } from "@/data/api";
import MorningGreeting from "@/components/MorningGreeting";
import BrandHeader from "@/components/BrandHeader";
import Deck from "@/components/Deck";
import StoryCard from "@/components/StoryCard";
import Link from "next/link";
import { applyFilters, deriveAvailableSources, parseFilters } from "@/utils/focusFilters";
import DataStatusBanner from "@/components/DataStatusBanner";

const MAX_STORIES = 7;

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
  const allStories = feedResult.stories;
  const availableSources = deriveAvailableSources(allStories);
  const urlParams = toURLSearchParams(resolvedSearchParams);
  const filters = parseFilters(urlParams);
  const filtered = applyFilters(allStories, filters);
  const stories = filtered.slice(0, MAX_STORIES);
  const hasFilters = urlParams.has("impact") || urlParams.has("sources");

  return (
    <div className="min-h-screen" style={{ background: "var(--paper)" }}>
      <div className="bg-ambient" />

      <div className="relative">
        {/* ── Desktop: single-flow brief (feed) ── */}
        <div className="hidden lg:block">
          <div className="sb-container px-4 py-2" style={{ maxWidth: 900 }}>
            <BrandHeader availableSources={availableSources} storyCount={stories.length} />
            <DataStatusBanner status={feedResult.status} />

            {stories.length > 0 ? (
              <div className="mt-6 space-y-4">
                <Link href={`/stories/${stories[0].story_id}`}>
                  <StoryCard story={stories[0]} variant="featured" />
                </Link>

                {stories.slice(1).map((story) => (
                  <Link key={story.story_id} href={`/stories/${story.story_id}`} className="block">
                    <StoryCard story={story} variant="compact" />
                  </Link>
                ))}

                <p className="text-center text-sm py-4" style={{ color: "var(--ink-muted)" }}>
                  You&apos;re all caught up. Enjoy your day.
                </p>
              </div>
            ) : (
              <EmptyState hasFilters={hasFilters} />
            )}
          </div>
        </div>

        {/* ── Mobile: greeting + card deck ── */}
        <div className="lg:hidden max-w-md mx-auto px-4">
          <MorningGreeting storyCount={stories.length} availableSources={availableSources} />
          <DataStatusBanner status={feedResult.status} />

          {stories.length > 0 ? (
            <div className="mt-3">
              <Deck stories={stories} />
            </div>
          ) : (
            <EmptyState hasFilters={hasFilters} />
          )}
        </div>
      </div>
    </div>
  );
}

function EmptyState({ hasFilters }: { hasFilters: boolean }) {
  return (
    <div className="text-center py-20 px-6">
      <p className="text-lg font-bold" style={{ color: "var(--ink)" }}>
        {hasFilters ? "No stories match your focus" : "Nothing new yet"}
      </p>
      <p className="text-sm mt-2" style={{ color: "var(--ink-muted)" }}>
        {hasFilters
          ? "Try clearing filters to see the full brief."
          : "Check back later — your morning brief is still being assembled."}
      </p>
      {hasFilters ? (
        <Link
          href="/"
          className="inline-block mt-4 text-sm font-bold sb-focusable px-4 py-2 rounded-xl"
          style={{ background: "var(--surface)", border: "1px solid var(--hairline)", color: "var(--ink)" }}
        >
          Clear filters
        </Link>
      ) : null}
    </div>
  );
}
