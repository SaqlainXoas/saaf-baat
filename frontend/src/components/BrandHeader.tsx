import FocusControl from "@/components/FocusControl";
import Logo from "@/components/Logo";
import ThemeToggle from "@/components/ThemeToggle";
import { formatEssentialStoryCount, getBriefEditionIdentity, getGreeting } from "@/utils/edition";

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
  availableSources = [],
  storyCount,
  generatedAt,
  isFresh,
}: {
  availableSources?: string[];
  storyCount?: number;
  generatedAt?: string;
  isFresh?: boolean;
}) {
  const city = process.env.NEXT_PUBLIC_CITY_NAME || "Islamabad";
  const edition = getBriefEditionIdentity(generatedAt, isFresh);
  const { greeting, translation } = getGreeting();

  return (
    <header className="sb-masthead">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <Logo size={26} decorative className="flex-shrink-0" />
          <span className="sb-wordmark">Saaf Baat</span>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <FocusControl availableSources={availableSources} size="sm" />
        </div>
      </div>

      <p className="sb-kicker sb-masthead-kicker">
        {edition.briefLabel} · {city} · {edition.stampLabel}
      </p>

      <h1 className="sb-display-home" lang="ur-Latn" title={translation}>
        {greeting}
      </h1>

      <p className="sb-masthead-note">
        {typeof storyCount === "number" ? `${formatEssentialStoryCount(storyCount)}, ` : ""}
        ranked for public impact. Read them and you&apos;re done.
      </p>
    </header>
  );
}
