import { FEED } from "@/data/mock-data";
import { fetchFeedWithMeta, fetchStoryWithMeta } from "@/data/api";
import { FEED_REQUEST_LIMIT } from "@/data/briefSize";

const ORIGINAL_BACKEND_API_BASE_URL = process.env.BACKEND_API_BASE_URL;
const ORIGINAL_PUBLIC_BACKEND_API_BASE_URL = process.env.NEXT_PUBLIC_BACKEND_API_BASE_URL;
const ORIGINAL_STRICT = process.env.NEXT_PUBLIC_STRICT_LIVE_DATA;
const ORIGINAL_NODE_ENV = process.env.NODE_ENV;

// NODE_ENV is declared readonly by @types/node; these tests exist to exercise
// the production/test branch in data/api.ts, so they must set it.
const mutableEnv = process.env as Record<string, string | undefined>;

describe("api data mode", () => {
  beforeEach(() => {
    jest.restoreAllMocks();
    delete process.env.BACKEND_API_BASE_URL;
    delete process.env.NEXT_PUBLIC_BACKEND_API_BASE_URL;
    delete process.env.NEXT_PUBLIC_STRICT_LIVE_DATA;
    mutableEnv.NODE_ENV = "test";
  });

  afterAll(() => {
    if (ORIGINAL_BACKEND_API_BASE_URL) process.env.BACKEND_API_BASE_URL = ORIGINAL_BACKEND_API_BASE_URL;
    else delete process.env.BACKEND_API_BASE_URL;
    if (ORIGINAL_PUBLIC_BACKEND_API_BASE_URL) {
      process.env.NEXT_PUBLIC_BACKEND_API_BASE_URL = ORIGINAL_PUBLIC_BACKEND_API_BASE_URL;
    } else {
      delete process.env.NEXT_PUBLIC_BACKEND_API_BASE_URL;
    }
    if (ORIGINAL_STRICT) process.env.NEXT_PUBLIC_STRICT_LIVE_DATA = ORIGINAL_STRICT;
    else delete process.env.NEXT_PUBLIC_STRICT_LIVE_DATA;
    if (ORIGINAL_NODE_ENV) mutableEnv.NODE_ENV = ORIGINAL_NODE_ENV;
  });

  it("uses mock data when backend API base is not configured", async () => {
    const result = await fetchFeedWithMeta();
    expect(result.status).toBe("mock-no-api");
    expect(result.stories).toEqual(FEED);
  });

  it("returns live status when backend feed call succeeds", async () => {
    process.env.BACKEND_API_BASE_URL = "http://127.0.0.1:8000";
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        generated_at: FEED[0].created_at,
        is_fresh: true,
        stories: [
          {
            story_id: FEED[0].story_id,
            created_at: FEED[0].created_at,
            headline: FEED[0].headline,
            snippet: FEED[0].snippet,
            category: FEED[0].category,
            impact_labels: FEED[0].impact_labels,
            sources: [{ source: "dawn", count: 1 }, { source: "geo", count: 1 }],
            metadata: { why_it_matters: "Fuel shifts affect household budgets." },
          },
        ],
      }),
    } as Response);

    const result = await fetchFeedWithMeta();
    expect(result.status).toBe("live");
    expect(result.stories).toHaveLength(1);
    expect(result.stories[0].sources).toEqual([
      { source: "dawn", count: 1 },
      { source: "geo", count: 1 },
    ]);
    expect(result.generatedAt).toBe(FEED[0].created_at);
    expect(result.isFresh).toBe(true);
    expect((global as unknown as { fetch: jest.Mock }).fetch.mock.calls[0][0]).toBe(
      `http://127.0.0.1:8000/api/feed?limit=${FEED_REQUEST_LIMIT}`,
    );
    expect((global as unknown as { fetch: jest.Mock }).fetch.mock.calls[0][1]).toMatchObject({
      // Tagged so publish_hosted.py can swap the cached edition the moment it
      // publishes. An untagged fetch makes revalidateTag a silent no-op.
      next: { tags: ["feed"] },
      headers: { Accept: "application/json" },
    });
  });

  it("uses the feed envelope freshness metadata instead of recomputing from ranked order", async () => {
    process.env.BACKEND_API_BASE_URL = "http://127.0.0.1:8000";
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        generated_at: "2026-02-04T06:30:00Z",
        is_fresh: false,
        stories: [
          {
            story_id: "older-ranked-higher",
            created_at: "2026-02-04T05:00:00Z",
            headline: "Higher priority but older",
            snippet: "Older story with stronger editorial priority.",
            category: "economy",
            impact_labels: ["💳 WALLET"],
            sources: [{ source: "dawn", count: 1 }],
            metadata: { editorial_priority: 100 },
          },
          {
            story_id: "newer-ranked-lower",
            created_at: "2026-02-04T06:30:00Z",
            headline: "Lower priority but newer",
            snippet: "Newer story that should drive freshness only.",
            category: "governance",
            impact_labels: ["🏛️ GOVERNANCE"],
            sources: [{ source: "geo", count: 1 }],
            metadata: { editorial_priority: 50 },
          },
        ],
      }),
    } as Response);

    const result = await fetchFeedWithMeta();
    expect(result.status).toBe("live");
    expect(result.stories[0].story_id).toBe("older-ranked-higher");
    expect(result.generatedAt).toBe("2026-02-04T06:30:00Z");
    expect(result.isFresh).toBe(false);
  });

  it("returns fallback status when backend feed call fails", async () => {
    process.env.BACKEND_API_BASE_URL = "http://127.0.0.1:8000";
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockRejectedValue(new Error("offline"));

    const result = await fetchFeedWithMeta();
    expect(result.status).toBe("mock-fallback");
    expect(result.stories.length).toBeGreaterThan(0);
  });

  it("hydrates story detail articles from backend story route", async () => {
    process.env.BACKEND_API_BASE_URL = "http://127.0.0.1:8000";
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        story_id: FEED[0].story_id,
        created_at: FEED[0].created_at,
        headline: FEED[0].headline,
        snippet: FEED[0].snippet,
        category: FEED[0].category,
        impact_labels: FEED[0].impact_labels,
        sources: [{ source: "dawn", count: 1 }],
        metadata: {
          why_it_matters: "Fuel changes hit households quickly.",
          what_to_watch: "Watch for an official statement.",
        },
        analysis: "Dawn reports that fuel changes will affect household bills.",
        question: "Which consumers will be protected from the increase?",
        articles: [
          {
            id: "article-1",
            source: "dawn",
            headline: "Dawn source",
            url: "https://www.dawn.com/news/123",
            publish_date: "2026-02-04T04:30:00Z",
          },
        ],
        analysis_sources: [
          {
            id: "article-2",
            source: "geo",
            headline: "Related consumer tariff reporting",
            url: "https://www.geo.tv/latest/456",
          },
        ],
      }),
    } as Response);

    const result = await fetchStoryWithMeta(FEED[0].story_id);
    expect(result.status).toBe("live");
    expect(result.story?.story_id).toBe(FEED[0].story_id);
    expect(result.story?.articles).toHaveLength(1);
    expect(result.story?.analysis).toContain("Dawn reports");
    expect(result.story?.question).toContain("Which consumers");
    expect(result.story?.analysis_sources).toHaveLength(1);
    expect(result.story?.metadata?.what_to_watch).toBe("Watch for an official statement.");
    expect(result.generatedAt).toBe(FEED[0].created_at);
    expect((global as unknown as { fetch: jest.Mock }).fetch.mock.calls[0][0]).toBe(
      `http://127.0.0.1:8000/api/stories/${FEED[0].story_id}`,
    );
  });

  it("returns not-found when backend story route returns 404", async () => {
    process.env.BACKEND_API_BASE_URL = "http://127.0.0.1:8000";
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({ detail: "Story not found" }),
    } as Response);

    const result = await fetchStoryWithMeta(FEED[0].story_id);
    expect(result.status).toBe("not-found");
    expect(result.story).toBeNull();
  });

  it("returns story fallback metadata when backend story query fails", async () => {
    process.env.BACKEND_API_BASE_URL = "http://127.0.0.1:8000";
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockRejectedValue(new Error("offline"));

    const result = await fetchStoryWithMeta(FEED[0].story_id);
    expect(result.status).toBe("mock-fallback");
    expect(result.story?.story_id).toBe(FEED[0].story_id);
  });

  it("blocks mock fallback in strict live mode when backend API base is missing", async () => {
    process.env.NEXT_PUBLIC_STRICT_LIVE_DATA = "1";
    const result = await fetchFeedWithMeta();
    expect(result.status).toBe("error-live-required");
    expect(result.stories).toEqual([]);
    expect(result.message).toContain("unavailable right now");
    expect(result.message).not.toContain("BACKEND_API_BASE_URL");
  });

  it("blocks story mock fallback in strict live mode when live request fails", async () => {
    process.env.NEXT_PUBLIC_STRICT_LIVE_DATA = "1";
    process.env.BACKEND_API_BASE_URL = "http://127.0.0.1:8000";
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValueOnce({
      ok: false,
      status: 503,
      json: async () => ({ detail: "Database unavailable" }),
    } as Response);

    const result = await fetchStoryWithMeta(FEED[0].story_id);
    expect(result.status).toBe("error-live-required");
    expect(result.story).toBeNull();
    expect(result.message).toContain("HTTP 503");
  });
  it("bounds a stalled backend request and returns a reader-friendly error", async () => {
    jest.useFakeTimers();
    process.env.NEXT_PUBLIC_STRICT_LIVE_DATA = "1";
    process.env.BACKEND_API_BASE_URL = "http://127.0.0.1:8000";
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn((_url, init) =>
      new Promise((_resolve, reject) => init.signal.addEventListener("abort", () => reject(new Error("aborted"))))
    );
    const pending = fetchFeedWithMeta();
    // Must exceed FETCH_TIMEOUT_MS in src/data/api.ts. That was 25s and this
    // line advanced exactly 25s, on a comment claiming it "allows for a Render
    // Free cold start" - it did not. A cold start outran it, every revalidation
    // that woke a sleeping Render aborted, and Vercel cached the error state
    // this test asserts instead of the brief.
    await jest.advanceTimersByTimeAsync(80_000);
    const result = await pending;
    expect(result.status).toBe("error-live-required");
    expect(result.stories).toEqual([]);
    expect(result.message).toBe("Unable to load brief. Please try again shortly.");
    jest.useRealTimers();
  });

});
