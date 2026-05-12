import type { SourceCountDTO, StoryCardData, StoryMetadata } from "@/data/types";

type StoryLike = Pick<
  StoryCardData,
  "headline" | "snippet" | "impact_labels" | "sources" | "metadata"
>;

const IMPACT_LANGUAGE: Record<string, string> = {
  "💳 WALLET": "household costs and the broader economic squeeze",
  "🚦 COMMUTE": "transport, logistics, and daily movement",
  "🛡️ SAFETY": "public safety and immediate security conditions",
  "🏢 WORK": "jobs, workplaces, and business continuity",
  "⚡ UTILITIES": "utilities, infrastructure, and service continuity",
  "🏛️ GOVERNANCE": "state response, policy, and public administration",
};

function asSentence(text: string) {
  const cleaned = (text || "").trim().replace(/\s+/g, " ");
  if (!cleaned) return "";
  return /[.!?]$/.test(cleaned) ? cleaned : `${cleaned}.`;
}

function quotedList(items: string[]) {
  if (items.length <= 1) return items[0] || "";
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items.at(-1)}`;
}

function toSourcePhrase(sources: SourceCountDTO[]) {
  const names = sources.map((source) => source.source.trim()).filter(Boolean);
  if (!names.length) return "Current reporting";
  const titled = names.map((name) => name.charAt(0).toUpperCase() + name.slice(1));
  return quotedList(titled);
}

function buildCoreDevelopmentSentence(sources: SourceCountDTO[]) {
  const sourcePhrase = toSourcePhrase(sources);
  if (sources.length <= 0) return "Current reporting points to the core development behind this brief.";
  if (sources.length === 1) return `Current reporting from ${sourcePhrase} points to the core development behind this brief.`;
  return `${sourcePhrase} line up on the core development behind this brief.`;
}

function getStoryTags(metadata?: StoryMetadata) {
  const raw = metadata?.story_tags;
  if (!Array.isArray(raw)) return [];
  return raw.map((tag) => String(tag).trim()).filter(Boolean).slice(0, 3);
}

function getImpactSentence(labels: string[]) {
  const mapped = labels.map((label) => IMPACT_LANGUAGE[label]).filter(Boolean).slice(0, 2);
  if (!mapped.length) return "";
  return `The practical impact sits in ${quotedList(mapped)}.`;
}

function buildAgreedItems(story: StoryLike) {
  const items: string[] = [];
  items.push(buildCoreDevelopmentSentence(story.sources));

  const tags = getStoryTags(story.metadata);
  if (tags.length) {
    items.push(`Coverage is centering on ${quotedList(tags)}.`);
  }

  const impacts = getImpactSentence(story.impact_labels || []);
  if (impacts) {
    items.push(impacts);
  } else if (story.metadata?.why_it_matters) {
    items.push(asSentence(String(story.metadata.why_it_matters)));
  } else if (story.snippet) {
    items.push(asSentence(story.snippet));
  }

  return items.filter(Boolean).slice(0, 3);
}

function buildDebatedItems(story: StoryLike) {
  const items: string[] = [];

  if (story.metadata?.what_to_watch) {
    items.push(asSentence(String(story.metadata.what_to_watch)));
  }

  if (!items.length && story.sources.length <= 1) {
    items.push("This item still leans on a single publisher and may sharpen as more reporting lands.");
  }

  if (!items.length) {
    items.push("Reporting aligns on the core event, and the next official update will sharpen the picture.");
  }

  return items.filter(Boolean).slice(0, 3);
}

export function getStoryPriority(story: Pick<StoryCardData, "created_at" | "metadata" | "story_id">) {
  const editorialPriority = Number(story.metadata?.editorial_priority ?? 0) || 0;
  const deterministicScore = Number(story.metadata?.deterministic_publish_score ?? 0) || 0;
  const createdAt = Date.parse(story.created_at || "") || 0;
  return { editorialPriority, deterministicScore, createdAt, storyId: story.story_id };
}

export function sortStoriesForBrief(stories: StoryCardData[]) {
  return [...stories].sort((left, right) => {
    const a = getStoryPriority(left);
    const b = getStoryPriority(right);
    return (
      b.editorialPriority - a.editorialPriority ||
      b.deterministicScore - a.deterministicScore ||
      b.createdAt - a.createdAt ||
      a.storyId.localeCompare(b.storyId)
    );
  });
}

export function buildConsensusSummary(story: StoryLike) {
  return {
    agreed: buildAgreedItems(story),
    debated: buildDebatedItems(story),
  };
}
