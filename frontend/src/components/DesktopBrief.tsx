"use client";

import Link from "next/link";
import BrandHeader from "@/components/BrandHeader";
import DataStatusBanner from "@/components/DataStatusBanner";
import StoryCard from "@/components/StoryCard";
import type { StoryCardData } from "@/data/types";
import type { DataStatus } from "@/data/api";

export default function DesktopBrief({
  stories,
  availableSources,
  status,
  statusMessage,
  latestCreatedAt,
}: {
  stories: StoryCardData[];
  availableSources: string[];
  status: Exclude<DataStatus, "not-found">;
  statusMessage?: string;
  latestCreatedAt?: string;
}) {
  const featuredStory = stories[0];
  const sidebarStories = stories.slice(1, 3);
  const lowerStories = stories.slice(3);

  if (!featuredStory) return null;

  return (
    <div className="sb-container px-6 py-8" style={{ maxWidth: 1240 }}>
      <BrandHeader availableSources={availableSources} storyCount={stories.length} />
      <DataStatusBanner status={status} message={statusMessage} latestCreatedAt={latestCreatedAt} />

      <section className="mt-12 grid grid-cols-12 gap-10 items-start">
        <div className="col-span-8">
          <div className="mb-7 max-w-2xl">
            <p className="sb-kicker">Lead story</p>
            <p className="text-sm mt-2 max-w-2xl" style={{ color: "var(--ink-muted)" }}>
              The strongest signal in today&apos;s brief, with the clearest reporting support and the most immediate public consequence.
            </p>
          </div>

          <Link href={`/stories/${featuredStory.story_id}`} className="block sb-focusable" data-testid="desktop-featured-preview">
            <StoryCard story={featuredStory} variant="featured" />
          </Link>
        </div>

        <aside className="col-span-4 space-y-5">
          <div className="sb-sidebar-note">
            <p className="sb-kicker" style={{ color: "var(--teal)" }}>
              Supporting stories
            </p>
            <p className="mt-3 text-2xl font-semibold tracking-tight" style={{ color: "var(--ink)" }}>
              The next strongest signals
            </p>
            <p className="mt-2 text-sm leading-relaxed" style={{ color: "var(--ink-muted)" }}>
              Read these after the lead to round out the morning picture without losing the ranking.
            </p>
          </div>

          {sidebarStories.map((story) => (
            <Link
              key={story.story_id}
              href={`/stories/${story.story_id}`}
              className="block sb-focusable"
              data-testid={`desktop-sidebar-${story.story_id}`}
            >
              <StoryCard story={story} variant="compact" />
            </Link>
          ))}
        </aside>
      </section>

      {lowerStories.length ? (
        <section className="mt-12">
          <div className="flex items-end justify-between gap-4 mb-5">
            <div>
              <p className="sb-kicker">More to know</p>
              <p className="text-sm mt-2" style={{ color: "var(--ink-muted)" }}>
                The rest of the brief, still ordered by importance.
              </p>
            </div>
            <p className="sb-meta">{lowerStories.length} more stories</p>
          </div>

          <div
            className={`grid gap-5 ${
              lowerStories.length === 1 ? "grid-cols-1 max-w-[420px]" : "grid-cols-1 md:grid-cols-2 xl:grid-cols-3"
            }`}
          >
            {lowerStories.map((story) => (
              <Link
                key={story.story_id}
                href={`/stories/${story.story_id}`}
                className="block sb-focusable"
                data-testid={`desktop-grid-${story.story_id}`}
              >
                <StoryCard story={story} variant="compact" />
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      <p className="text-center text-sm py-10" style={{ color: "var(--ink-muted)" }}>
        You&apos;re all caught up. The brief ends here on purpose.
      </p>
    </div>
  );
}
