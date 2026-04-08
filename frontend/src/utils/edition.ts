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

export function formatEssentialStoryCount(storyCount: number) {
  return `${storyCount} essential stor${storyCount === 1 ? "y" : "ies"}`;
}
