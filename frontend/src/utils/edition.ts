function resolveEditionDate(dateInput?: string | Date | null, fallback = new Date()) {
  if (dateInput instanceof Date) {
    return Number.isNaN(dateInput.getTime()) ? fallback : dateInput;
  }

  if (typeof dateInput === "string") {
    const parsed = new Date(dateInput);
    if (!Number.isNaN(parsed.getTime())) {
      return parsed;
    }
  }

  return fallback;
}

export function formatEditionDate(dateInput?: string | Date | null) {
  const date = resolveEditionDate(dateInput);
  return new Intl.DateTimeFormat("en-PK", {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone: "Asia/Karachi",
  }).format(date);
}

export function formatEditionStamp(dateInput?: string | Date | null) {
  const date = resolveEditionDate(dateInput);
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "Asia/Karachi",
  }).format(date);
}

function toPakistanDateParts(date: Date) {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Karachi",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  const parts = formatter.formatToParts(date);
  const lookup = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${lookup.year}-${lookup.month}-${lookup.day}`;
}

function toPakistanHour(date: Date) {
  const hour = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Karachi",
    hour: "2-digit",
    hourCycle: "h23",
  }).format(date);
  return Number(hour);
}

export function isMorningEditionFresh(
  generatedAt?: string | null,
  now = new Date(),
  editionHour = 5,
) {
  if (!generatedAt) return false;
  const generated = new Date(generatedAt);
  if (Number.isNaN(generated.getTime())) return false;
  const age = now.getTime() - generated.getTime();
  return (
    age >= 0 &&
    age <= 20 * 60 * 60 * 1000 &&
    toPakistanDateParts(generated) === toPakistanDateParts(now) &&
    toPakistanHour(generated) >= editionHour
  );
}

export function isCurrentEdition(generatedAt?: string | null, isFresh?: boolean, now = new Date()) {
  if (isFresh === false) {
    return false;
  }

  const parsedGeneratedAt = generatedAt ? new Date(generatedAt) : null;
  if (!parsedGeneratedAt || Number.isNaN(parsedGeneratedAt.getTime())) {
    return true;
  }

  return toPakistanDateParts(parsedGeneratedAt) === toPakistanDateParts(now);
}

export function getBriefEditionIdentity(generatedAt?: string | null, isFresh?: boolean, now = new Date()) {
  const editionDate = resolveEditionDate(generatedAt, now);
  const currentEdition = isCurrentEdition(generatedAt, isFresh, now);
  return {
    isCurrentEdition: currentEdition,
    title: formatBriefEditionTitle(generatedAt, isFresh, now),
    dateLabel: formatEditionDate(editionDate),
    stampLabel: formatEditionStamp(editionDate),
    editionLabel: currentEdition ? "Today's edition" : "Latest edition",
    briefLabel: currentEdition ? "Today's brief" : "Latest brief",
    backLinkLabel: currentEdition ? "Today's Brief" : "Latest Brief",
    rankingNote: currentEdition
      ? "Ranked for public impact first."
      : "Last available brief, ranked for public impact first.",
  };
}

export function formatBriefEditionTitle(generatedAt?: string | null, isFresh?: boolean, now = new Date()) {
  const editionDate = resolveEditionDate(generatedAt, now);

  const todayLabel = new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    timeZone: "Asia/Karachi",
  }).format(editionDate);

  if (isCurrentEdition(generatedAt, isFresh, now)) {
    return `Today's Brief · ${todayLabel}`;
  }

  const archiveLabel = new Intl.DateTimeFormat("en-US", {
    month: "long",
    day: "numeric",
    timeZone: "Asia/Karachi",
  }).format(editionDate);
  return `Morning Brief · ${archiveLabel}`;
}

export type GreetingBand = "morning" | "midday" | "evening";

/**
 * The three things the masthead can open with, on the Karachi clock:
 *
 *   05:00-11:59  Subah Bakhair   Good morning
 *   12:00-16:59  Aaj Ki Baat     Today's word
 *   17:00-04:59  Shaam Bakhair   Good evening
 *
 * The midday band is deliberately *not* a greeting. This brief is produced
 * once, early; an earlier hour-varying version greeted the same morning
 * edition "Assalam-o-alaikum" at 2pm, re-badging a morning product as an
 * afternoon one. "Aaj Ki Baat" is a masthead label, so the afternoon reader
 * gets an honest heading rather than the wrong greeting.
 *
 * All three are rendered into the h1 on every request, and CSS reveals one of
 * them off `data-pkt-band` on <html> (see PKT_BAND_SCRIPT). That is not a
 * flourish: pages are prerendered and served from Vercel's cache, so a
 * greeting baked in at render time would still say "Subah Bakhair" at 20:00.
 * Resolving it in CSS means the server and the client render identical markup
 * - nothing here can differ between server render and hydration - while the
 * band itself is chosen in the browser, before first paint.
 */
export const GREETING_BANDS = [
  { band: "morning", greeting: "Subah Bakhair", translation: "Good morning" },
  { band: "midday", greeting: "Aaj Ki Baat", translation: "Today's word" },
  { band: "evening", greeting: "Shaam Bakhair", translation: "Good evening" },
] as const satisfies ReadonlyArray<{ band: GreetingBand; greeting: string; translation: string }>;

/**
 * `at` is either a Date - read as an hour in Asia/Karachi, never in the
 * server's, the build machine's or the reader's zone - or a PKT hour 0-23
 * passed directly, so the bands are unit testable without mocking a clock.
 */
export function getGreetingBand(at: Date | number = new Date()): GreetingBand {
  const hour = typeof at === "number" ? at : toPakistanHour(at);
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 17) return "midday";
  return "evening";
}

export function getGreeting(at?: Date | number) {
  const band = getGreetingBand(at);
  const { greeting, translation } = GREETING_BANDS.find((entry) => entry.band === band)!;
  return { greeting, translation };
}

/**
 * The band picker, as a blocking inline script for the document head.
 *
 * It duplicates the boundaries in `getGreetingBand` because it has to run
 * before React and before first paint, with no module loader. The pairing is
 * held by a test that evaluates this string for all 24 hours and compares it
 * against `getGreetingBand`. If you change a boundary, change both.
 *
 * A throw leaves the attribute unset, and the stylesheet's default shows the
 * morning band - which is also what a reader with JavaScript off sees.
 */
export const PKT_BAND_SCRIPT =
  '(function(){try{var h=+new Intl.DateTimeFormat("en-GB",{timeZone:"Asia/Karachi",' +
  'hour:"2-digit",hourCycle:"h23"}).format(new Date());' +
  'document.documentElement.dataset.pktBand=h<5?"evening":h<12?"morning":h<17?"midday":"evening";}' +
  "catch(e){}})();";

export function formatEssentialStoryCount(storyCount: number) {
  return `${storyCount} essential stor${storyCount === 1 ? "y" : "ies"}`;
}
