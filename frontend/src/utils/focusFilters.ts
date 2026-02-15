import type { StoryCardData } from "@/data/types";
import { IMPACT_LABELS, type ImpactLabel, normaliseImpact } from "@/utils/impact";

export type FocusFilters = {
  impacts: Set<ImpactLabel>;
  sources: Set<string>;
};

const KNOWN_SOURCE_ORDER: string[] = ["dawn", "geo", "tribune"];

function splitCsv(value: string | null): string[] {
  if (!value) return [];
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function parseFilters(params: URLSearchParams): FocusFilters {
  const impacts = new Set<ImpactLabel>();
  const sources = new Set<string>();

  for (const raw of splitCsv(params.get("impact"))) {
    const upper = raw.toUpperCase();
    if ((IMPACT_LABELS as readonly string[]).includes(upper)) impacts.add(upper as ImpactLabel);
  }

  for (const raw of splitCsv(params.get("sources"))) {
    sources.add(raw.toLowerCase());
  }

  return { impacts, sources };
}

export function serialiseFilters(filters: FocusFilters): { impact?: string; sources?: string } {
  const impact = Array.from(filters.impacts).join(",");
  const sources = Array.from(filters.sources).join(",");
  return {
    impact: impact.length ? impact : undefined,
    sources: sources.length ? sources : undefined,
  };
}

export function applyFilters(stories: StoryCardData[], filters: FocusFilters): StoryCardData[] {
  const hasImpact = filters.impacts.size > 0;
  const hasSources = filters.sources.size > 0;

  if (!hasImpact && !hasSources) return stories;

  return stories.filter((story) => {
    if (hasImpact) {
      const primary = normaliseImpact(story.impact_labels?.[0] || "");
      if (primary === "UPDATE") return false;
      if (!filters.impacts.has(primary)) return false;
    }

    if (hasSources) {
      const storySources = story.sources?.map((s) => s.source.toLowerCase()) || [];
      if (!storySources.some((s) => filters.sources.has(s))) return false;
    }

    return true;
  });
}

export function deriveAvailableSources(stories: StoryCardData[]): string[] {
  const found = new Set<string>();
  for (const story of stories) {
    for (const s of story.sources || []) found.add(s.source.toLowerCase());
  }

  const rest = Array.from(found).filter((s) => !KNOWN_SOURCE_ORDER.includes(s)).sort();
  return [...KNOWN_SOURCE_ORDER.filter((s) => found.has(s)), ...rest];
}
