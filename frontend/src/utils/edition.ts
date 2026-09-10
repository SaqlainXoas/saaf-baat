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
  editionHour = 7,
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

/**
 * The greeting the brief opens with.
 *
 * Always "Subah bakhair". This is a *morning* brief - it is produced once, early,
 * and that is what it is. An earlier version varied the greeting by the hour in
 * Karachi, which meant a reader opening the same morning's brief after midday
 * was greeted "Assalam-o-alaikum" as though it were an afternoon product. The
 * greeting names the edition, not the moment the page was loaded.
 *
 * Being a constant also removes a whole class of bug: nothing here can differ
 * between the server render and hydration.
 */
export function getGreeting() {
  return { greeting: "Subah bakhair", translation: "Good morning" };
}

export function formatEssentialStoryCount(storyCount: number) {
  return `${storyCount} essential stor${storyCount === 1 ? "y" : "ies"}`;
}
