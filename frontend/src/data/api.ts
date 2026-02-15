import type { StoryCardData, StoryDetailData } from "./types";
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
};

type StoryResult = {
  story: StoryDetailData | null;
  status: DataStatus;
  message?: string;
};

function getApiBase() {
  return process.env.NEXT_PUBLIC_API_URL?.trim() || "";
}

function isStrictLiveMode() {
  const raw = process.env.NEXT_PUBLIC_STRICT_LIVE_DATA?.trim().toLowerCase();
  if (raw === "1" || raw === "true") return true;
  if (raw === "0" || raw === "false") return false;
  return process.env.NODE_ENV === "production";
}

export async function fetchFeedWithMeta(): Promise<FeedResult> {
  const apiBase = getApiBase();
  const strictLive = isStrictLiveMode();
  if (!apiBase) {
    if (strictLive) {
      return {
        stories: [],
        status: "error-live-required",
        message: "Live data mode is enabled but NEXT_PUBLIC_API_URL is not configured.",
      };
    }
    return { stories: FEED, status: "mock-no-api" };
  }

  try {
    const res = await fetch(`${apiBase}/api/feed`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) {
      if (strictLive) {
        return {
          stories: [],
          status: "error-live-required",
          message: `Live feed request failed with HTTP ${res.status}.`,
        };
      }
      throw new Error(`HTTP ${res.status}`);
    }
    const stories = (await res.json()) as StoryCardData[];
    return { stories, status: "live" };
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
  const apiBase = getApiBase();
  const strictLive = isStrictLiveMode();
  if (!apiBase) {
    if (strictLive) {
      return {
        story: null,
        status: "error-live-required",
        message: "Live data mode is enabled but NEXT_PUBLIC_API_URL is not configured.",
      };
    }
    return {
      story: getMockDetail(clusterId),
      status: "mock-no-api",
    };
  }

  try {
    const res = await fetch(`${apiBase}/api/stories/${clusterId}`, {
      next: { revalidate: 300 },
    });

    if (res.ok) {
      const story = (await res.json()) as StoryDetailData;
      return { story, status: "live" };
    }

    if (res.status === 404) return { story: null, status: "not-found" };
    if (strictLive) {
      return {
        story: null,
        status: "error-live-required",
        message: `Live story request failed with HTTP ${res.status}.`,
      };
    }

    const fallback = getMockDetail(clusterId);
    if (fallback) return { story: fallback, status: "mock-fallback" };
    return { story: null, status: "not-found" };
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
