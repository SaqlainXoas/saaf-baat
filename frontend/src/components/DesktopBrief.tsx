"use client";

import { useMemo, useState } from "react";
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
  const defaultStoryId = stories[0]?.story_id || "";
  const [activeStoryId, setActiveStoryId] = useState(defaultStoryId);

  const activeStory = useMemo(() => {
    if (!stories.length) return null;
    return stories.find((story) => story.story_id === activeStoryId) || stories[0];
  }, [activeStoryId, stories]);
  const compactStories = useMemo(
    () => stories.filter((story) => story.story_id !== activeStory?.story_id),
    [activeStory?.story_id, stories],
  );

  function resetPreview() {
    setActiveStoryId(defaultStoryId);
  }

  if (!stories.length || !activeStory) return null;

  return (
    <div className="sb-container px-4 py-2" style={{ maxWidth: 900 }}>
      <BrandHeader availableSources={availableSources} storyCount={stories.length} />
      <DataStatusBanner status={status} message={statusMessage} latestCreatedAt={latestCreatedAt} />

      <div className="mt-5 grid grid-cols-1 gap-4">
        <div className="sticky top-3 z-10" data-testid="desktop-featured-preview">
          <Link href={`/stories/${activeStory.story_id}`} className="block">
            <div key={activeStory.story_id} className="sb-featured-enter">
              <StoryCard story={activeStory} variant="featured" />
            </div>
          </Link>
        </div>

        <div
          data-testid="desktop-compact-list"
          className="space-y-3"
          onMouseLeave={resetPreview}
          onBlurCapture={(event) => {
            const next = event.relatedTarget as Node | null;
            if (!event.currentTarget.contains(next)) resetPreview();
          }}
        >
          {compactStories.map((story, index) => (
            <Link
              key={story.story_id}
              href={`/stories/${story.story_id}`}
              className="block"
              data-testid={`desktop-compact-${story.story_id}`}
              onMouseEnter={() => setActiveStoryId(story.story_id)}
              onFocus={() => setActiveStoryId(story.story_id)}
              style={{ animationDelay: `${Math.min(index * 40, 180)}ms` }}
            >
              <div className="sb-list-stagger-in">
                <StoryCard story={story} variant="compact" />
              </div>
            </Link>
          ))}
        </div>

        <p className="text-center text-sm py-4" style={{ color: "var(--ink-muted)" }}>
          You&apos;re all caught up. Enjoy your day.
        </p>
      </div>
    </div>
  );
}
