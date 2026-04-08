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
          <p className="text-sm mt-1" style={{ color: "var(--ink-muted)" }}>
            Start with the lead story, then skim the rest in ranked order.
          </p>
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

      <div>
        <p className="sb-kicker mb-3" style={{ color: "var(--teal)" }}>
          Lead story
        </p>
        <Link href={`/stories/${leadStory.story_id}`} className="block sb-focusable">
          <StoryCard story={leadStory} variant="featured" />
        </Link>
      </div>

      {supportingStories.length ? (
        <div className="mt-8">
          <div className="flex items-end justify-between gap-3 mb-4">
            <div>
              <p className="sb-kicker">Also moving</p>
              <p className="text-sm mt-1" style={{ color: "var(--ink-muted)" }}>
                The next strongest stories in the brief.
              </p>
            </div>
            <span className="sb-meta">{supportingStories.length} stories</span>
          </div>
          <div className="space-y-4">
            {supportingStories.map((story) => (
              <Link key={story.story_id} href={`/stories/${story.story_id}`} className="block sb-focusable">
                <StoryCard story={story} variant="compact" />
              </Link>
            ))}
          </div>
        </div>
      ) : null}

      {lowerStories.length ? (
        <div className="mt-8">
          <div className="flex items-end justify-between gap-3 mb-4">
            <div>
              <p className="sb-kicker">Then worth your time</p>
              <p className="text-sm mt-1" style={{ color: "var(--ink-muted)" }}>
                The rest of the brief, still ordered by importance.
              </p>
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
