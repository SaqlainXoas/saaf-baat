import type { AnalyzedFeedRow, StoryCardData, StoryDetailData } from "./types";
import { FEED, getMockDetail } from "./mock-data";

export type DataStatus =
  | "live"
  | "mock-no-api"
  | "mock-fallback"
  | "not-found"
  | "error-live-required";

type FeedResult = {
  stories: StoryCardData[];
  status: Exclude<DataStatus, "not-found">;
  message?: string;
  latestPipelineRunAt?: string;
};

type StoryResult = {
  story: StoryDetailData | null;
  status: DataStatus;
  message?: string;
  latestPipelineRunAt?: string;
};

function getSupabaseConfig() {
  const url = process.env.SUPABASE_URL?.trim() || process.env.NEXT_PUBLIC_SUPABASE_URL?.trim() || "";
  const anonKey =
    process.env.SUPABASE_ANON_KEY?.trim() ||
    process.env.SUPABASE_KEY?.trim() ||
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim() ||
    "";
  return { url, anonKey };
}

function isStrictLiveMode() {
  const raw = process.env.NEXT_PUBLIC_STRICT_LIVE_DATA?.trim().toLowerCase();
  if (raw === "1" || raw === "true") return true;
  if (raw === "0" || raw === "false") return false;
  return process.env.NODE_ENV === "production";
}

export async function fetchFeedWithMeta(): Promise<FeedResult> {
  const { url: supabaseUrl, anonKey } = getSupabaseConfig();
  const strictLive = isStrictLiveMode();
  if (!supabaseUrl || !anonKey) {
    if (strictLive) {
      return {
        stories: [],
        status: "error-live-required",
        message:
          "Live data mode is enabled but Supabase env is missing (SUPABASE_URL + SUPABASE_ANON_KEY).",
      };
    }
    return { stories: FEED, status: "mock-no-api" };
  }

  try {
    const stories = await fetchSupabaseFeed({
      supabaseUrl,
      anonKey,
      limit: 9,
    });
    const latestPipelineRunAt = stories[0]?.created_at;
    return { stories, status: "live", latestPipelineRunAt };
  } catch {
    if (strictLive) {
      return {
        stories: [],
        status: "error-live-required",
        message: "Live feed request failed and strict mode blocks mock fallback.",
      };
    }
    return { stories: FEED, status: "mock-fallback" };
  }
}

export async function fetchFeed(): Promise<StoryCardData[]> {
  const result = await fetchFeedWithMeta();
  return result.stories;
}

export async function fetchStoryWithMeta(clusterId: string): Promise<StoryResult> {
  const { url: supabaseUrl, anonKey } = getSupabaseConfig();
  const strictLive = isStrictLiveMode();
  if (!supabaseUrl || !anonKey) {
    if (strictLive) {
      return {
        story: null,
        status: "error-live-required",
        message:
          "Live data mode is enabled but Supabase env is missing (SUPABASE_URL + SUPABASE_ANON_KEY).",
      };
    }
    return {
      story: getMockDetail(clusterId),
      status: "mock-no-api",
    };
  }

  try {
    const story = await fetchSupabaseStoryDetail({
      supabaseUrl,
      anonKey,
      clusterId,
    });
    if (!story) return { story: null, status: "not-found" };
    const latestPipelineRunAt = story.created_at;
    return { story, status: "live", latestPipelineRunAt };
  } catch {
    if (strictLive) {
      return {
        story: null,
        status: "error-live-required",
        message: "Live story request failed and strict mode blocks mock fallback.",
      };
    }
    const fallback = getMockDetail(clusterId);
    if (fallback) return { story: fallback, status: "mock-fallback" };
    return { story: null, status: "not-found" };
  }
}

export async function fetchStory(
  clusterId: string,
): Promise<StoryDetailData | null> {
  const result = await fetchStoryWithMeta(clusterId);
  return result.story;
}

type SupabaseAnalyzedFeedRow = AnalyzedFeedRow & { is_published?: boolean | null };

function supabaseHeaders(anonKey: string) {
  return {
    apikey: anonKey,
    Authorization: `Bearer ${anonKey}`,
    Accept: "application/json",
  } as const;
}

function toStoryCard(row: SupabaseAnalyzedFeedRow): StoryCardData {
  const rawAttribution = row.source_attribution || {};
  const sources = Object.entries(rawAttribution)
    .map(([source, count]) => ({
      source,
      count: typeof count === "number" ? count : Number.parseInt(String(count), 10) || 0,
    }))
    .filter((s) => s.source && s.count > 0)
    .sort((a, b) => b.count - a.count || a.source.localeCompare(b.source));

  return {
    story_id: row.cluster_id,
    created_at: row.created_at,
    headline: row.headline,
    snippet: row.summary || "",
    category: row.category,
    impact_labels: row.impact_labels || [],
    confirmed_facts: Array.isArray(row.confirmed_facts) ? (row.confirmed_facts as any) : [],
    debated_claims: Array.isArray(row.debated_claims) ? (row.debated_claims as any) : [],
    sources,
    metadata: row.metadata || {},
  };
}

async function fetchSupabaseFeed({
  supabaseUrl,
  anonKey,
  limit,
}: {
  supabaseUrl: string;
  anonKey: string;
  limit: number;
}): Promise<StoryCardData[]> {
  const url = new URL("/rest/v1/analyzed_feed", supabaseUrl);
  url.searchParams.set(
    "select",
    [
      "cluster_id",
      "created_at",
      "headline",
      "summary",
      "category",
      "impact_labels",
      "confirmed_facts",
      "debated_claims",
      "source_attribution",
      "metadata",
      "is_published",
    ].join(","),
  );
  url.searchParams.set("is_published", "eq.true");
  url.searchParams.set("order", "created_at.desc");
  url.searchParams.set("limit", String(limit));

  const res = await fetch(url.toString(), {
    headers: supabaseHeaders(anonKey),
    next: { revalidate: 300, tags: ["feed"] },
  });
  if (!res.ok) throw new Error(`Supabase feed HTTP ${res.status}`);
  const rows = (await res.json()) as SupabaseAnalyzedFeedRow[];
  return rows.map(toStoryCard);
}

async function fetchSupabaseStoryDetail({
  supabaseUrl,
  anonKey,
  clusterId,
}: {
  supabaseUrl: string;
  anonKey: string;
  clusterId: string;
}): Promise<StoryDetailData | null> {
  const url = new URL("/rest/v1/analyzed_feed", supabaseUrl);
  url.searchParams.set(
    "select",
    [
      "cluster_id",
      "created_at",
      "headline",
      "summary",
      "category",
      "impact_labels",
      "confirmed_facts",
      "debated_claims",
      "source_attribution",
      "metadata",
      "is_published",
    ].join(","),
  );
  url.searchParams.set("cluster_id", `eq.${clusterId}`);
  url.searchParams.set("is_published", "eq.true");
  url.searchParams.set("order", "created_at.desc");
  url.searchParams.set("limit", "1");

  const res = await fetch(url.toString(), {
    headers: supabaseHeaders(anonKey),
    next: { revalidate: 300, tags: [`story:${clusterId}`, "feed"] },
  });
  if (!res.ok) throw new Error(`Supabase story HTTP ${res.status}`);
  const rows = (await res.json()) as SupabaseAnalyzedFeedRow[];
  const row = rows[0];
  if (!row) return null;
  return {
    ...toStoryCard(row),
    articles: [],
  };
}
