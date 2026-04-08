import type { AnalyzedFeedRow, StoryArticleData, StoryCardData, StoryDetailData } from "./types";
import { FEED, getMockDetail } from "./mock-data";
import { sortStoriesForBrief } from "@/utils/storyPresentation";

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

type ApiStoryDetailRow = AnalyzedFeedRow & {
  story_id?: string;
  snippet?: string;
  sources?: StoryCardData["sources"];
  articles?: StoryArticleData[];
};

class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

function normaliseApiBase(raw: string) {
  const trimmed = raw.trim().replace(/\/+$/, "");
  if (!trimmed) return "";
  if (trimmed === "/api" || trimmed.endsWith("/api")) return trimmed;
  return `${trimmed}/api`;
}

function getBackendApiBase() {
  const explicit =
    process.env.BACKEND_API_BASE_URL?.trim() ||
    process.env.NEXT_PUBLIC_BACKEND_API_BASE_URL?.trim() ||
    process.env.API_BASE_URL?.trim() ||
    process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ||
    "";

  if (explicit) return normaliseApiBase(explicit);

  const siteUrl =
    process.env.SITE_URL?.trim() ||
    process.env.NEXT_PUBLIC_SITE_URL?.trim() ||
    (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : "");
  if (siteUrl) return normaliseApiBase(siteUrl);

  if (process.env.NODE_ENV === "development") {
    return "http://127.0.0.1:8000/api";
  }

  return "";
}

function isStrictLiveMode() {
  const raw = process.env.NEXT_PUBLIC_STRICT_LIVE_DATA?.trim().toLowerCase();
  if (raw === "1" || raw === "true") return true;
  if (raw === "0" || raw === "false") return false;
  return process.env.NODE_ENV === "production";
}

function missingApiMessage() {
  return "Live data mode is enabled but the backend API base is missing (set BACKEND_API_BASE_URL or NEXT_PUBLIC_BACKEND_API_BASE_URL).";
}

function liveFetchFailureMessage(status?: number) {
  if (status) return `Live briefing is unavailable right now. Backend request failed with HTTP ${status}.`;
  return "Live briefing is unavailable right now.";
}

function buildApiUrl(baseUrl: string, path: string) {
  const cleanPath = path.replace(/^\/+/, "");
  if (baseUrl.startsWith("http://") || baseUrl.startsWith("https://")) {
    return new URL(cleanPath, `${baseUrl}/`).toString();
  }
  return `${baseUrl}/${cleanPath}`;
}

function toStoryCard(row: ApiStoryDetailRow): StoryCardData {
  const sources = Array.isArray(row.sources)
    ? row.sources
    : Object.entries(row.source_attribution || {})
        .map(([source, count]) => ({
          source,
          count: typeof count === "number" ? count : Number.parseInt(String(count), 10) || 0,
        }))
        .filter((source) => source.source && source.count > 0)
        .sort((a, b) => b.count - a.count || a.source.localeCompare(b.source));

  return {
    story_id: row.story_id || row.cluster_id,
    created_at: row.created_at,
    headline: row.headline,
    snippet: row.snippet ?? row.summary ?? "",
    category: row.category,
    impact_labels: row.impact_labels || [],
    confirmed_facts: Array.isArray(row.confirmed_facts) ? (row.confirmed_facts as StoryCardData["confirmed_facts"]) : [],
    debated_claims: Array.isArray(row.debated_claims) ? (row.debated_claims as StoryCardData["debated_claims"]) : [],
    sources,
    metadata: row.metadata || {},
  };
}

function toStoryDetail(row: ApiStoryDetailRow): StoryDetailData {
  return {
    ...toStoryCard(row),
    articles: Array.isArray(row.articles) ? row.articles : [],
  };
}

async function fetchJson<T>(input: string) {
  const response = await fetch(input, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new ApiRequestError(`Request failed with HTTP ${response.status}`, response.status);
  }
  return (await response.json()) as T;
}

async function fetchBackendFeed(baseUrl: string, limit: number): Promise<StoryCardData[]> {
  const url = buildApiUrl(baseUrl, `/feed?limit=${limit}`);
  const rows = await fetchJson<ApiStoryDetailRow[]>(url);
  return sortStoriesForBrief(rows.map(toStoryCard));
}

async function fetchBackendStory(baseUrl: string, clusterId: string): Promise<StoryDetailData | null> {
  const url = buildApiUrl(baseUrl, `/stories/${clusterId}`);
  const row = await fetchJson<ApiStoryDetailRow>(url);
  return row ? toStoryDetail(row) : null;
}

function getLatestCreatedAt(stories: Pick<StoryCardData, "created_at">[]) {
  let latest: string | undefined;
  let latestTime = 0;

  stories.forEach((story) => {
    const createdAt = story.created_at?.trim();
    if (!createdAt) return;

    const parsed = Date.parse(createdAt);
    if (Number.isNaN(parsed) || parsed <= latestTime) return;

    latestTime = parsed;
    latest = createdAt;
  });

  return latest;
}

export async function fetchFeedWithMeta(): Promise<FeedResult> {
  const backendApiBase = getBackendApiBase();
  const strictLive = isStrictLiveMode();

  if (!backendApiBase) {
    if (strictLive) {
      return { stories: [], status: "error-live-required", message: missingApiMessage() };
    }
    return { stories: FEED, status: "mock-no-api" };
  }

  try {
    const stories = await fetchBackendFeed(backendApiBase, 9);
    return {
      stories,
      status: "live",
      latestPipelineRunAt: getLatestCreatedAt(stories),
    };
  } catch (error) {
    if (strictLive) {
      return {
        stories: [],
        status: "error-live-required",
        message:
          error instanceof ApiRequestError
            ? liveFetchFailureMessage(error.status)
            : "Live feed request failed and strict mode blocks mock fallback.",
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
  const backendApiBase = getBackendApiBase();
  const strictLive = isStrictLiveMode();

  if (!backendApiBase) {
    if (strictLive) {
      return { story: null, status: "error-live-required", message: missingApiMessage() };
    }
    return { story: getMockDetail(clusterId), status: "mock-no-api" };
  }

  try {
    const story = await fetchBackendStory(backendApiBase, clusterId);
    if (!story) return { story: null, status: "not-found" };
    return {
      story,
      status: "live",
      latestPipelineRunAt: story.created_at,
    };
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 404) {
      return { story: null, status: "not-found" };
    }
    if (strictLive) {
      return {
        story: null,
        status: "error-live-required",
        message:
          error instanceof ApiRequestError
            ? liveFetchFailureMessage(error.status)
            : "Live story request failed and strict mode blocks mock fallback.",
      };
    }
    const fallback = getMockDetail(clusterId);
    if (fallback) return { story: fallback, status: "mock-fallback" };
    return { story: null, status: "not-found" };
  }
}

export async function fetchStory(clusterId: string): Promise<StoryDetailData | null> {
  const result = await fetchStoryWithMeta(clusterId);
  return result.story;
}
