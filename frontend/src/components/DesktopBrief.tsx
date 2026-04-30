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
  if (!stories.length) return null;

  return (
    <div className="sb-container px-6 py-8" style={{ maxWidth: 1240 }}>
      <BrandHeader availableSources={availableSources} storyCount={stories.length} />
      <div className="mt-3 max-w-[980px]">
        <DataStatusBanner status={status} message={statusMessage} latestCreatedAt={latestCreatedAt} />
      </div>

      <section className="mt-4 max-w-[980px] xl:pr-10">
          <div className="sb-brief-flow">
          {stories.map((story, index) => (
            <div
              key={story.story_id}
              id={index === 0 ? "lead-story" : undefined}
              tabIndex={index === 0 ? -1 : undefined}
            >
              <Link
                href={`/stories/${story.story_id}`}
                className="block sb-focusable"
                data-testid={`desktop-story-${story.story_id}`}
                data-skip-target={index === 0 ? "stories" : undefined}
              >
                <StoryCard story={story} variant="homepage" />
              </Link>
            </div>
          ))}
          </div>
      </section>

      <p className="max-w-[980px] text-sm py-7" style={{ color: "var(--ink-muted)" }}>
        You&apos;re all caught up. The brief ends here on purpose.
      </p>
    </div>
  );
}
