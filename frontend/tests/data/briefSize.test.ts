import { MAX_STORIES, FEED_REQUEST_LIMIT } from "@/data/briefSize";

describe("brief size", () => {
  it("matches the backend's 10-12 card target", () => {
    expect(MAX_STORIES).toBe(12);
  });

  it("requests more rows than it displays", () => {
    // The backend applies `limit` at the database level and only then sorts by
    // editorial priority. Requesting exactly MAX_STORIES cut the day's
    // highest-priority card before it was ever ranked.
    expect(FEED_REQUEST_LIMIT).toBeGreaterThan(MAX_STORIES);
  });
});
