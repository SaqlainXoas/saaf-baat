import { FEED } from "@/data/mock-data";
import { fetchFeedWithMeta, fetchStoryWithMeta } from "@/data/api";

const ORIGINAL_API_URL = process.env.NEXT_PUBLIC_API_URL;
const ORIGINAL_STRICT = process.env.NEXT_PUBLIC_STRICT_LIVE_DATA;

describe("api data mode", () => {
  beforeEach(() => {
    jest.restoreAllMocks();
    delete process.env.NEXT_PUBLIC_API_URL;
    delete process.env.NEXT_PUBLIC_STRICT_LIVE_DATA;
  });

  afterAll(() => {
    if (ORIGINAL_API_URL) process.env.NEXT_PUBLIC_API_URL = ORIGINAL_API_URL;
    else delete process.env.NEXT_PUBLIC_API_URL;
    if (ORIGINAL_STRICT) process.env.NEXT_PUBLIC_STRICT_LIVE_DATA = ORIGINAL_STRICT;
    else delete process.env.NEXT_PUBLIC_STRICT_LIVE_DATA;
  });

  it("uses mock data when API URL is not configured", async () => {
    const result = await fetchFeedWithMeta();
    expect(result.status).toBe("mock-no-api");
    expect(result.stories).toEqual(FEED);
  });

  it("returns live status when API call succeeds", async () => {
    process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000";
    (global as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [FEED[0]],
    } as Response);

    const result = await fetchFeedWithMeta();
    expect(result.status).toBe("live");
    expect(result.stories).toHaveLength(1);
  });

  it("returns fallback status when API call fails", async () => {
    process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000";
    (global as { fetch: jest.Mock }).fetch = jest.fn().mockRejectedValue(new Error("offline"));

    const result = await fetchFeedWithMeta();
    expect(result.status).toBe("mock-fallback");
    expect(result.stories.length).toBeGreaterThan(0);
  });

  it("returns story fallback metadata when story endpoint fails", async () => {
    process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000";
    (global as { fetch: jest.Mock }).fetch = jest.fn().mockRejectedValue(new Error("offline"));

    const result = await fetchStoryWithMeta(FEED[0].story_id);
    expect(result.status).toBe("mock-fallback");
    expect(result.story?.story_id).toBe(FEED[0].story_id);
  });

  it("blocks mock fallback in strict live mode when API URL is missing", async () => {
    process.env.NEXT_PUBLIC_STRICT_LIVE_DATA = "1";
    const result = await fetchFeedWithMeta();
    expect(result.status).toBe("error-live-required");
    expect(result.stories).toEqual([]);
  });

  it("blocks story mock fallback in strict live mode when request fails", async () => {
    process.env.NEXT_PUBLIC_STRICT_LIVE_DATA = "1";
    process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000";
    (global as { fetch: jest.Mock }).fetch = jest.fn().mockRejectedValue(new Error("offline"));

    const result = await fetchStoryWithMeta(FEED[0].story_id);
    expect(result.status).toBe("error-live-required");
    expect(result.story).toBeNull();
  });
});
