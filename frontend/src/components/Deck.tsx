"use client";

import Link from "next/link";
import StoryCard from "./StoryCard";
import BriefProgress from "./BriefProgress";
import type { StoryCardData } from "@/data/types";
import { useBriefProgress } from "@/hooks/useBriefProgress";
import { getBriefEditionIdentity } from "@/utils/edition";

/**
 * The mobile brief: one numbered deck, not three ranked sections.
 *
 * The "Top story" / "Next up" / "Then worth your time" headings are gone. With
 * every card carrying its own position the rank *is* the order, and the
 * headings re-introduced the "am I done yet?" question the counter answers.
 *
 * Snapping is `proximity`, never `mandatory`: a reader skims a brief and skips
 * what they already know, and twelve mandatory full-screen stops would make it
 * slower to get through than a plain list. Native scrolling throughout - no
 * carousel library, no touch handlers, so keyboard and screen-reader behaviour
 * is untouched.
 */
export default function Deck({
  stories,
  generatedAt,
  isFresh,
}: {
  stories: StoryCardData[];
  generatedAt?: string;
  isFresh?: boolean;
}) {
  const editionIdentity = getBriefEditionIdentity(generatedAt, isFresh);
  const { position, register } = useBriefProgress(stories.length);

  if (!stories.length) return null;

  return (
    <section aria-label="Morning brief">
      {/* The masthead directly above already says what this is and how many
          cards there are; a second "start at the top and move fast" line under
          it was the same sentence twice. Only the edition label survives, and
          only because it changes when the brief is stale. */}
      <p className="sb-kicker mb-2">{editionIdentity.briefLabel}</p>

      <BriefProgress position={position} total={stories.length} />

      <div className="sb-deck">
        {stories.map((story, index) => (
          <article
            key={story.story_id}
            className={`sb-deck-item ${index === 0 ? "sb-deck-item-lead" : ""}`}
            data-brief-index={index}
            id={index === 0 ? "mobile-lead-story" : undefined}
            tabIndex={index === 0 ? -1 : undefined}
            ref={register(index)}
          >
            {/* The sticky bar above carries "n / total"; repeating the total
                on every card said the same thing twice. */}
            <p className="sb-deck-rank" aria-hidden="true">
              <span className="sb-deck-rank-number">{index + 1}</span>
            </p>
            <Link
              href={`/stories/${story.story_id}`}
              className="block sb-focusable"
              data-skip-target={index === 0 ? "stories" : undefined}
            >
              <StoryCard story={story} variant={index === 0 ? "lead" : "supporting"} />
            </Link>
          </article>
        ))}
      </div>

      <BriefEnd />
    </section>
  );
}

/** The brief ends on purpose, and says so. */
export function BriefEnd() {
  return (
    <div className="sb-brief-end">
      <span className="sb-brief-end-rule" aria-hidden="true" />
      <p className="sb-brief-end-title">You&apos;re all caught up.</p>
      <p className="sb-brief-end-note">
        The brief ends here on purpose. There is no more to scroll — come back tomorrow morning.
      </p>
    </div>
  );
}
