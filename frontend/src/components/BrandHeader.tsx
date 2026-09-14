import Logo from "@/components/Logo";
import ThemeToggle from "@/components/ThemeToggle";
import MastheadGreeting from "@/components/MastheadGreeting";
import { formatEssentialStoryCount, getBriefEditionIdentity } from "@/utils/edition";

/**
 * The desktop masthead.
 *
 * It used to say the same things three times: the story count appeared in the
 * kicker, in a status pill and in the ranking note, and the date appeared in
 * both the kicker and the display title. Nine text elements stood between the
 * top of the page and the first headline.
 *
 * Now: who and where, the greeting, and one sentence about what the reader is
 * holding. The greeting is the thing this product opens with.
 */
export default function BrandHeader({
  storyCount,
  generatedAt,
  isFresh,
}: {
  storyCount?: number;
  generatedAt?: string;
  isFresh?: boolean;
}) {
  const city = "Pakistan";
  const edition = getBriefEditionIdentity(generatedAt, isFresh);

  return (
    <header className="sb-masthead">
      <div className="sb-brand-row flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <Logo size={26} decorative className="flex-shrink-0" />
          <span className="sb-wordmark">Saaf Baat</span>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
        </div>
      </div>

      <p className="sb-kicker sb-masthead-kicker">
        {edition.briefLabel} · {city} · {edition.stampLabel}
      </p>

      <MastheadGreeting className="sb-display-home" />

      <p className="sb-masthead-note">
        {typeof storyCount === "number" ? `${formatEssentialStoryCount(storyCount)}. ` : ""}
        What happened and why it matters.
      </p>
    </header>
  );
}
