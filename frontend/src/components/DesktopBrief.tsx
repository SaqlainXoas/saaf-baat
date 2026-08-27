"use client";

import Link from "next/link";
import BrandHeader from "@/components/BrandHeader";
import BriefProgress from "@/components/BriefProgress";
import DataStatusBanner from "@/components/DataStatusBanner";
import StoryCard from "@/components/StoryCard";
import { BriefEnd } from "@/components/Deck";
import { useBriefProgress } from "@/hooks/useBriefProgress";
import type { StoryCardData } from "@/data/types";
import type { DataStatus } from "@/data/api";

/**
 * The desktop brief.
 *
 * It was a 980px column of identical rows inside a 1240px shell: no rank
 * numerals, no progress, no distinction between the day's lead story and the
 * eleventh, and ~260px of dead margin on the right. Mobile got the deck
 * treatment and desktop kept the list, so the wider screen showed strictly
 * less than the phone did.
 *
 * Now it is the same brief in a shape that suits the width: a reading column
 * held to a comfortable measure, and a sticky rail in the space that was empty
 * carrying the counter. Same cards, same ranks, same ending as mobile.
 */
export default function DesktopBrief({
  stories,
  availableSources,
  status,
  statusMessage,
  generatedAt,
  isFresh,
}: {
  stories: StoryCardData[];
  availableSources: string[];
  status: Exclude<DataStatus, "not-found">;
  statusMessage?: string;
  generatedAt?: string;
  isFresh?: boolean;
}) {
  const { position, register } = useBriefProgress(stories.length);

  if (!stories.length) return null;

  return (
    <div className="sb-desktop-shell">
      <BrandHeader
        availableSources={availableSources}
        storyCount={stories.length}
        generatedAt={generatedAt}
        isFresh={isFresh}
      />

      <div className="sb-desktop-banner">
        <DataStatusBanner
          status={status}
          message={statusMessage}
          generatedAt={generatedAt}
          isFresh={isFresh}
          storyCount={stories.length}
        />
      </div>

      <div className="sb-desktop-grid">
        <section className="sb-desktop-column" aria-label="Morning brief">
          {stories.map((story, index) => (
            <article
              key={story.story_id}
              className={`sb-brief-item ${index === 0 ? "sb-brief-item-lead" : ""}`}
              data-brief-index={index}
              id={index === 0 ? "lead-story" : undefined}
              tabIndex={index === 0 ? -1 : undefined}
              ref={register(index)}
            >
              <p className="sb-deck-rank" aria-hidden="true">
                <span className="sb-deck-rank-number">{index + 1}</span>
              </p>
              <Link
                href={`/stories/${story.story_id}`}
                className="block sb-focusable"
                data-testid={`desktop-story-${story.story_id}`}
                data-skip-target={index === 0 ? "stories" : undefined}
              >
                <StoryCard story={story} variant={index === 0 ? "lead" : "supporting"} />
              </Link>
            </article>
          ))}

          <BriefEnd />
        </section>

        {/* The right-hand space was dead margin. It now carries the one thing
            desktop was missing: how far through a finite brief you are. */}
        <aside className="sb-desktop-rail" aria-hidden="true">
          <div className="sb-desktop-rail-inner">
            <p className="sb-kicker">Your progress</p>
            <BriefProgress position={position} total={stories.length} variant="static" />
            <p className="sb-rail-note">
              This brief is finite. When the cards run out, you have read everything
              Saaf Baat thinks matters today.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
