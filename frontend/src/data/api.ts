import type { StoryCardData, StoryDetailData } from "./types";
import { FEED, getMockDetail } from "./mock-data";

export type DataStatus = "live" | "mock-no-api" | "mock-fallback" | "not-found";

type FeedResult = {
  stories: StoryCardData[];
  status: Exclude<DataStatus, "not-found">;
};

type StoryResult = {
  story: StoryDetailData | null;
  status: DataStatus;
};

function getApiBase() {
  return process.env.NEXT_PUBLIC_API_URL?.trim() || "";
}

export async function fetchFeedWithMeta(): Promise<FeedResult> {
  const apiBase = getApiBase();
  if (!apiBase) return { stories: FEED, status: "mock-no-api" };

  try {
    const res = await fetch(`${apiBase}/api/feed`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const stories = (await res.json()) as StoryCardData[];
    return { stories, status: "live" };
  } catch {
    return { stories: FEED, status: "mock-fallback" };
  }
}

export async function fetchFeed(): Promise<StoryCardData[]> {
  const result = await fetchFeedWithMeta();
  return result.stories;
}

export async function fetchStoryWithMeta(clusterId: string): Promise<StoryResult> {
  const apiBase = getApiBase();
  if (!apiBase) {
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

    const fallback = getMockDetail(clusterId);
    if (fallback) return { story: fallback, status: "mock-fallback" };
    return { story: null, status: "not-found" };
  } catch {
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
