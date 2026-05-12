export function formatEditionDate(date = new Date()) {
  return new Intl.DateTimeFormat("en-PK", {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone: "Asia/Karachi",
  }).format(date);
}

export function formatEditionStamp(date = new Date()) {
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

export function formatBriefEditionTitle(generatedAt?: string | null, now = new Date()) {
  const parsedGeneratedAt = generatedAt ? new Date(generatedAt) : null;
  const hasGeneratedAt = parsedGeneratedAt && !Number.isNaN(parsedGeneratedAt.getTime());
  const editionDate = hasGeneratedAt ? parsedGeneratedAt : now;

  const todayLabel = new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    timeZone: "Asia/Karachi",
  }).format(editionDate);

  if (!hasGeneratedAt) {
    return `Today's Brief · ${todayLabel}`;
  }

  const isTodayInPakistan = toPakistanDateParts(parsedGeneratedAt) === toPakistanDateParts(now);
  if (isTodayInPakistan) {
    return `Today's Brief · ${todayLabel}`;
  }

  const archiveLabel = new Intl.DateTimeFormat("en-US", {
    month: "long",
    day: "numeric",
    timeZone: "Asia/Karachi",
  }).format(parsedGeneratedAt);
  return `Morning Brief · ${archiveLabel}`;
}

export function formatEssentialStoryCount(storyCount: number) {
  return `${storyCount} essential stor${storyCount === 1 ? "y" : "ies"}`;
}
