import { PHASE_PRODUCTION_BUILD } from "next/constants";
import { fetchFeedWithMeta } from "@/data/api";
import { MAX_STORIES } from "@/data/briefSize";
import BrandHeader from "@/components/BrandHeader";
import MorningGreeting from "@/components/MorningGreeting";
import DesktopBrief from "@/components/DesktopBrief";
import Deck from "@/components/Deck";
import DataStatusBanner from "@/components/DataStatusBanner";
import SkipLink from "@/components/SkipLink";


export default async function Home() {
  const feedResult = await fetchFeedWithMeta();
  const hasLiveDataError = feedResult.status === "error-live-required";
  // At request time a failed backend fetch must throw, not render. The home
  // page is cached, so a rendered "Unable to load brief" would be served to
  // every reader until the next revalidation; a throw is never cached - Vercel
  // keeps the last good edition and retries on the next request.
  //
  // Not during `next build`, where this page is prerendered: there a throw
  // fails the whole build, and CI builds with no backend while a Vercel deploy
  // can land on a sleeping Render. The build renders the error state instead,
  // and the first successful revalidation replaces it.
  if (hasLiveDataError && process.env.NEXT_PHASE !== PHASE_PRODUCTION_BUILD) {
    throw new Error(feedResult.message || "Unable to load brief.");
  }
  // No render-time filter: the API guarantees why_it_matters on every card
  // (see backend test_api_feed_route). A client-side filter over a backend
  // contract gap silently shrinks the brief instead of failing loudly (I-7).
  const stories = feedResult.stories.slice(0, MAX_STORIES);
  const generatedAt = feedResult.generatedAt;

  return (
    <div className="min-h-screen" style={{ background: "var(--paper)" }}>
      <div className="bg-ambient" />
      <SkipLink label="Skip to stories" selector='[data-skip-target="stories"]' />

      <main id="main-content" className="relative" role="main">
        {/* ── Tablet and desktop: the brief column, with the progress rail
             appearing at 1024 where there is room for it.

             This was `lg:` (1024px), which left 768-1023 rendering the phone
             deck inside a 416px `max-w-md` column in a 768px viewport - most
             of a tablet screen empty either side. The desktop layout minus its
             rail is exactly the right shape for that width. ── */}
        <div className="hidden md:block">
          {hasLiveDataError ? (
            <div className="sb-container px-4 py-2" style={{ maxWidth: 900 }}>
              <LiveDataErrorState message={feedResult.message} />
            </div>
          ) : stories.length > 0 ? (
            <DesktopBrief
              stories={stories}
              status={feedResult.status}
              statusMessage={feedResult.message}
              generatedAt={generatedAt}
              isFresh={feedResult.isFresh}
            />
          ) : (
            <div className="sb-container px-4 py-2" style={{ maxWidth: 900 }}>
              <BrandHeader storyCount={0} generatedAt={generatedAt} isFresh={feedResult.isFresh} />
              <EmptyState />
            </div>
          )}
        </div>

        {/* ── Phone: greeting + card deck ── */}
        <div className="md:hidden max-w-md mx-auto px-4">
          <MorningGreeting
            storyCount={stories.length}
            generatedAt={generatedAt}
            isFresh={feedResult.isFresh}
          />
          {!hasLiveDataError && <DataStatusBanner
            status={feedResult.status}
            message={feedResult.message}
            generatedAt={generatedAt}
            isFresh={feedResult.isFresh}
            storyCount={stories.length}
          />}

          {hasLiveDataError ? (
            <LiveDataErrorState compact message={feedResult.message} />
          ) : stories.length > 0 ? (
            <div className="mt-3">
              <Deck stories={stories} generatedAt={generatedAt} isFresh={feedResult.isFresh} />
            </div>
          ) : (
            <EmptyState />
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
      {/* A full navigation retries the server request instead of cached client state. */}
      {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
      <a
        href="/"
        className="inline-block mt-4 text-sm font-bold sb-focusable px-4 py-2 rounded-xl"
        style={{ background: "var(--surface)", border: "1px solid var(--hairline)", color: "var(--ink)" }}
      >
        Retry
      </a>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="text-center py-20 px-6">
      <p className="text-lg font-bold" style={{ color: "var(--ink)" }}>The morning brief is being prepared</p>
      <p className="text-sm mt-2" style={{ color: "var(--ink-muted)" }}>Check back after 7am PKT.</p>
    </div>
  );
}
