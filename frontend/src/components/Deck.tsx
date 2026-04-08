"use client";

import Link from "next/link";
import StoryCard from "./StoryCard";
import type { StoryCardData } from "@/data/types";

export default function Deck({ stories }: { stories: StoryCardData[] }) {
  const [leadStory, ...remainingStories] = stories;
  const supportingStories = remainingStories.slice(0, 2);
  const lowerStories = remainingStories.slice(2);

  if (!leadStory) return null;

  return (
    <section aria-label="Morning brief">
      <div className="flex items-end justify-between gap-3 mb-4">
        <div>
          <p className="sb-kicker">Today&apos;s brief</p>
          <p className="sb-meta mt-1">Start at the top and move fast through the rest.</p>
        </div>
        <span
          className="text-xs font-medium rounded-full px-2.5 py-1"
          style={{
            background: "color-mix(in srgb, var(--surface) 88%, var(--surface-base))",
            border: "1px solid color-mix(in srgb, var(--outline-ghost) 72%, transparent)",
            color: "var(--ink-muted)",
          }}
        >
          {stories.length} stories
        </span>
      </div>

      <div id="mobile-lead-story" tabIndex={-1}>
        <p className="sb-kicker mb-3" style={{ color: "var(--teal)" }}>
          Top story
        </p>
        <Link href={`/stories/${leadStory.story_id}`} className="block sb-focusable" data-skip-target="stories">
          <StoryCard story={leadStory} variant="featured" />
        </Link>
      </div>

      {supportingStories.length ? (
        <div className="mt-6">
          <div className="flex items-end justify-between gap-3 mb-4">
            <div>
              <p className="sb-kicker">Next up</p>
              <p className="sb-meta mt-1">The next strongest stories in rank order.</p>
            </div>
            <span className="sb-meta">{supportingStories.length} stories</span>
          </div>
          <div className="space-y-4">
            {supportingStories.map((story) => (
              <Link key={story.story_id} href={`/stories/${story.story_id}`} className="block sb-focusable">
                <StoryCard story={story} variant="supporting" />
              </Link>
            ))}
          </div>
        </div>
      ) : null}

      {lowerStories.length ? (
        <div className="mt-6">
          <div className="flex items-end justify-between gap-3 mb-4">
            <div>
              <p className="sb-kicker">Then worth your time</p>
              <p className="sb-meta mt-1">The rest of the brief, still ordered by importance.</p>
            </div>
            <span className="sb-meta">{lowerStories.length} more</span>
          </div>
          <div className="space-y-4">
            {lowerStories.map((story) => (
              <Link key={story.story_id} href={`/stories/${story.story_id}`} className="block sb-focusable">
                <StoryCard story={story} variant="compact" />
              </Link>
            ))}
          </div>
        </div>
      ) : null}

      <p className="text-center text-sm mt-8 leading-relaxed" style={{ color: "var(--ink-muted)" }}>
        You&apos;re all caught up.<br />The brief ends here on purpose.
      </p>
    </section>
  );
}
