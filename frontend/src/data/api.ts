import type {
  AnalyzedFeedRow,
  FeedResponseData,
  StoryArticleData,
  StoryCardData,
  StoryDetailData,
} from "./types";
import { FEED, getMockDetail } from "./mock-data";
import { sortStoriesForBrief } from "@/utils/storyPresentation";
import { isMorningEditionFresh } from "@/utils/edition";
import { FEED_REQUEST_LIMIT } from "./briefSize";

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
  generatedAt?: string;
  isFresh?: boolean;
};

type StoryResult = {
  story: StoryDetailData | null;
  status: DataStatus;
  message?: string;
  generatedAt?: string;
  isFresh?: boolean;
};

type ApiStoryDetailRow = AnalyzedFeedRow & {
  story_id?: string;
  snippet?: string;
  sources?: StoryCardData["sources"];
  articles?: StoryArticleData[];
  analysis?: string | null;
  question?: string | null;
  analysis_sources?: StoryArticleData[];
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
  return "The brief is unavailable right now. Please try again shortly.";
}

function liveFetchFailureMessage(status?: number) {
  if (status) return `Unable to load brief. Please try again shortly. (HTTP ${status})`;
  return "Unable to load brief. Please try again shortly.";
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
    sources,
    metadata: row.metadata || {},
  };
}

function toStoryDetail(row: ApiStoryDetailRow): StoryDetailData {
  return {
    ...toStoryCard(row),
    analysis: typeof row.analysis === "string" && row.analysis.trim() ? row.analysis.trim() : null,
    question: typeof row.question === "string" && row.question.trim() ? row.question.trim() : null,
    articles: Array.isArray(row.articles) ? row.articles : [],
    analysis_sources: Array.isArray(row.analysis_sources) ? row.analysis_sources : [],
  };
}

// Render Free sleeps and wakes in roughly a minute. Fetching per request with
// `no-store` made every cold visit wait on that wake-up and then fail the 8s
// abort, so the first reader of the day saw the retry state instead of the
// brief. These responses are tagged and cached instead: Vercel serves the last
// good edition straight from its cache while the backend wakes, and
// `publish_hosted.py` calls /api/revalidate to swap in a new edition the moment
// it publishes. REVALIDATE_WINDOW_SECONDS is only the fallback for a run whose
// revalidate ping did not land.
const REVALIDATE_WINDOW_SECONDS = 900;
// Render Free takes longer than 25s to cold-start, which is what 25_000 was.
// A revalidation that lands on a sleeping backend therefore always aborted,
// and the abort is what gets cached - so the page sat on "Unable to load
// brief" while the API, the pipeline and Supabase were all healthy. The
// pipeline now wakes Render before it asks for a revalidation; this is the
// second line of defence, for a cold start nobody warmed. It only bounds a
// background re-render, not a reader: Vercel serves the cached edition while
// that runs.
const FETCH_TIMEOUT_MS = 75_000;

async function fetchJson<T>(input: string, tags: string[]) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(input, {
      headers: { Accept: "application/json" },
      next: { tags, revalidate: REVALIDATE_WINDOW_SECONDS },
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new ApiRequestError(`Request failed with HTTP ${response.status}`, response.status);
    }
    return (await response.json()) as T;
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchBackendFeed(baseUrl: string, limit: number): Promise<FeedResponseData> {
  const url = buildApiUrl(baseUrl, `/feed?limit=${limit}`);
  return fetchJson<FeedResponseData>(url, ["feed"]);
}

async function fetchBackendStory(baseUrl: string, clusterId: string): Promise<StoryDetailData | null> {
  const url = buildApiUrl(baseUrl, `/stories/${clusterId}`);
  const row = await fetchJson<ApiStoryDetailRow>(url, ["feed", "story"]);
  return row ? toStoryDetail(row) : null;
}

function isFreshBrief(generatedAt?: string | null) {
  return isMorningEditionFresh(generatedAt);
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
    const payload = await fetchBackendFeed(backendApiBase, FEED_REQUEST_LIMIT);
    const stories = sortStoriesForBrief((payload.stories || []).map(toStoryCard));
    return {
      stories,
      status: "live",
      generatedAt: payload.generated_at || undefined,
      isFresh: payload.is_fresh,
    };
  } catch (error) {
    if (strictLive) {
      return {
        stories: [],
        status: "error-live-required",
        message:
          error instanceof ApiRequestError
            ? liveFetchFailureMessage(error.status)
            : liveFetchFailureMessage(),
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
      generatedAt: story.created_at,
      isFresh: isFreshBrief(story.created_at),
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
            : liveFetchFailureMessage(),
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
