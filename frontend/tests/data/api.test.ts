import { FEED } from "@/data/mock-data";
import { fetchFeedWithMeta, fetchStoryWithMeta } from "@/data/api";

const ORIGINAL_SUPABASE_URL = process.env.SUPABASE_URL;
const ORIGINAL_SUPABASE_ANON_KEY = process.env.SUPABASE_ANON_KEY;
const ORIGINAL_STRICT = process.env.NEXT_PUBLIC_STRICT_LIVE_DATA;

describe("api data mode", () => {
  beforeEach(() => {
    jest.restoreAllMocks();
    delete process.env.SUPABASE_URL;
    delete process.env.SUPABASE_ANON_KEY;
    delete process.env.NEXT_PUBLIC_STRICT_LIVE_DATA;
  });

  afterAll(() => {
    if (ORIGINAL_SUPABASE_URL) process.env.SUPABASE_URL = ORIGINAL_SUPABASE_URL;
    else delete process.env.SUPABASE_URL;
    if (ORIGINAL_SUPABASE_ANON_KEY) process.env.SUPABASE_ANON_KEY = ORIGINAL_SUPABASE_ANON_KEY;
    else delete process.env.SUPABASE_ANON_KEY;
    if (ORIGINAL_STRICT) process.env.NEXT_PUBLIC_STRICT_LIVE_DATA = ORIGINAL_STRICT;
    else delete process.env.NEXT_PUBLIC_STRICT_LIVE_DATA;
  });

  it("uses mock data when Supabase env is not configured", async () => {
    const result = await fetchFeedWithMeta();
    expect(result.status).toBe("mock-no-api");
    expect(result.stories).toEqual(FEED);
  });

  it("returns live status when Supabase call succeeds", async () => {
    process.env.SUPABASE_URL = "https://example.supabase.co";
    process.env.SUPABASE_ANON_KEY = "anon";
    (global as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => [
        {
          cluster_id: FEED[0].story_id,
          created_at: FEED[0].created_at,
          headline: FEED[0].headline,
          summary: FEED[0].snippet,
          category: FEED[0].category,
          impact_labels: FEED[0].impact_labels,
          confirmed_facts: FEED[0].confirmed_facts,
          debated_claims: FEED[0].debated_claims,
          source_attribution: { dawn: 1, geo: 1 },
          metadata: {},
          is_published: true,
        },
      ],
    } as Response);

    const result = await fetchFeedWithMeta();
    expect(result.status).toBe("live");
    expect(result.stories).toHaveLength(1);
    expect(result.latestPipelineRunAt).toBe(FEED[0].created_at);
  });

  it("returns fallback status when Supabase call fails", async () => {
    process.env.SUPABASE_URL = "https://example.supabase.co";
    process.env.SUPABASE_ANON_KEY = "anon";
    (global as { fetch: jest.Mock }).fetch = jest.fn().mockRejectedValue(new Error("offline"));

    const result = await fetchFeedWithMeta();
    expect(result.status).toBe("mock-fallback");
    expect(result.stories.length).toBeGreaterThan(0);
  });

  it("returns story fallback metadata when story query fails", async () => {
    process.env.SUPABASE_URL = "https://example.supabase.co";
    process.env.SUPABASE_ANON_KEY = "anon";
    (global as { fetch: jest.Mock }).fetch = jest.fn().mockRejectedValue(new Error("offline"));

    const result = await fetchStoryWithMeta(FEED[0].story_id);
    expect(result.status).toBe("mock-fallback");
    expect(result.story?.story_id).toBe(FEED[0].story_id);
  });

  it("returns story live metadata when Supabase story query succeeds", async () => {
    process.env.SUPABASE_URL = "https://example.supabase.co";
    process.env.SUPABASE_ANON_KEY = "anon";
    (global as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => [
        {
          cluster_id: FEED[0].story_id,
          created_at: FEED[0].created_at,
          headline: FEED[0].headline,
          summary: FEED[0].snippet,
          category: FEED[0].category,
          impact_labels: FEED[0].impact_labels,
          confirmed_facts: FEED[0].confirmed_facts,
          debated_claims: FEED[0].debated_claims,
          source_attribution: { dawn: 1 },
          metadata: {},
          is_published: true,
        },
      ],
    } as Response);

    const result = await fetchStoryWithMeta(FEED[0].story_id);
    expect(result.status).toBe("live");
    expect(result.story?.story_id).toBe(FEED[0].story_id);
    expect(result.latestPipelineRunAt).toBe(FEED[0].created_at);
  });

  it("blocks mock fallback in strict live mode when Supabase env is missing", async () => {
    process.env.NEXT_PUBLIC_STRICT_LIVE_DATA = "1";
    const result = await fetchFeedWithMeta();
    expect(result.status).toBe("error-live-required");
    expect(result.stories).toEqual([]);
  });

  it("blocks story mock fallback in strict live mode when request fails", async () => {
    process.env.NEXT_PUBLIC_STRICT_LIVE_DATA = "1";
    process.env.SUPABASE_URL = "https://example.supabase.co";
    process.env.SUPABASE_ANON_KEY = "anon";
    (global as { fetch: jest.Mock }).fetch = jest.fn().mockRejectedValue(new Error("offline"));

    const result = await fetchStoryWithMeta(FEED[0].story_id);
    expect(result.status).toBe("error-live-required");
    expect(result.story).toBeNull();
  });
});
