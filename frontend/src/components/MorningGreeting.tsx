"use client";

import Logo from "@/components/Logo";
import ThemeToggle from "@/components/ThemeToggle";
import { formatEssentialStoryCount, getBriefEditionIdentity, getGreeting } from "@/utils/edition";

/**
 * The mobile masthead: the greeting the brief opens with.
 *
 * Trimmed from eight stacked text elements down to four. The old header put a
 * wordmark, a kicker, a city chip, a date, a title, a tagline, a count chip and
 * two more taglines above the first card - on a phone that is most of a screen
 * spent before any news.
 */
export default function MorningGreeting({
  storyCount,
  generatedAt,
  isFresh,
}: {
  storyCount: number;
  generatedAt?: string;
  isFresh?: boolean;
}) {
  const city = "Pakistan";
  const edition = getBriefEditionIdentity(generatedAt, isFresh);
  const { greeting, translation } = getGreeting();

  return (
    <header className="sb-masthead sb-masthead-mobile">
      <div className="sb-brand-row flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 flex-shrink-0">
          <Logo size={24} decorative className="flex-shrink-0" />
          <span className="sb-wordmark">Saaf Baat</span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <ThemeToggle />
        </div>
      </div>

      <p className="sb-kicker sb-masthead-kicker">
        {city} · {edition.dateLabel}
      </p>

      <h1 className="sb-display-mobile" lang="ur-Latn" title={translation}>
        {greeting}
      </h1>

      <p className="sb-masthead-note">
        {storyCount > 0 ? `${formatEssentialStoryCount(storyCount)}. ` : ""}What happened and why it matters.
      </p>
    </header>
  );
}
