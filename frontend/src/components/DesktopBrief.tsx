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

      <section className="mt-8">
        <div className="mb-5 flex items-end justify-between gap-4">
          <div>
            <p className="sb-kicker">Top of the brief</p>
            <p className="sb-meta mt-2">Start here, then move through the next strongest stories.</p>
          </div>
          <p className="sb-meta">{stories.length} ranked stories</p>
        </div>

        <div className="grid grid-cols-12 gap-5 items-start">
          <div id="lead-story" tabIndex={-1} className="col-span-12 xl:col-span-6">
            <Link
              href={`/stories/${featuredStory.story_id}`}
              className="block sb-focusable"
              data-testid="desktop-featured-preview"
              data-skip-target="stories"
            >
              <StoryCard story={featuredStory} variant="featured" />
            </Link>
          </div>

          {sidebarStories.map((story) => (
            <div key={story.story_id} className="col-span-12 md:col-span-6 xl:col-span-3">
              <Link
                href={`/stories/${story.story_id}`}
                className="block sb-focusable h-full"
                data-testid={`desktop-sidebar-${story.story_id}`}
              >
                <StoryCard story={story} variant="supporting" />
              </Link>
            </div>
          ))}
        </div>
      </section>

      {lowerStories.length ? (
        <section className="mt-10">
          <div className="flex items-end justify-between gap-4 mb-5">
            <div>
              <p className="sb-kicker">More to know</p>
              <p className="sb-meta mt-2">The rest of the brief, still ordered by importance.</p>
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
