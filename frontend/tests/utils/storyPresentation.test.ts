import type { StoryCardData } from "@/data/types";
import {
  buildConsensusSummary,
  getStoryPriority,
  sortStoriesForBrief,
} from "@/utils/storyPresentation";

function story(partial: Partial<StoryCardData> & { story_id: string }): StoryCardData {
  return {
    created_at: "2026-08-25T06:00:00Z",
    headline: "Headline",
    snippet: "Snippet.",
    category: "economy",
    impact_labels: [],
    sources: [{ source: "dawn", count: 1 }],
    metadata: {},
    ...partial,
  };
}

describe("sortStoriesForBrief", () => {
  it("puts the editor's priority first", () => {
    const sorted = sortStoriesForBrief([
      story({ story_id: "low", metadata: { editorial_priority: 20 } }),
      story({ story_id: "high", metadata: { editorial_priority: 95 } }),
    ]);
    expect(sorted.map((s) => s.story_id)).toEqual(["high", "low"]);
  });

  it("breaks a priority tie on source breadth, not on a deleted score", () => {
    // The tiebreak used to read `deterministic_publish_score`, which the
    // backend stopped writing in Phase 4 - so it was always 0 and ordered
    // nothing. Corroboration is a fact the API still ships.
    const sorted = sortStoriesForBrief([
      story({ story_id: "thin", metadata: { editorial_priority: 60 } }),
      story({
        story_id: "corroborated",
        metadata: { editorial_priority: 60 },
        sources: [
          { source: "dawn", count: 1 },
          { source: "geo", count: 1 },
          { source: "ary", count: 1 },
        ],
      }),
    ]);
    expect(sorted.map((s) => s.story_id)).toEqual(["corroborated", "thin"]);
  });

  it("falls through to recency, then to a stable id order", () => {
    const sorted = sortStoriesForBrief([
      story({ story_id: "older", created_at: "2026-08-25T04:00:00Z" }),
      story({ story_id: "newer", created_at: "2026-08-25T09:00:00Z" }),
    ]);
    expect(sorted.map((s) => s.story_id)).toEqual(["newer", "older"]);

    const identical = sortStoriesForBrief([story({ story_id: "b" }), story({ story_id: "a" })]);
    expect(identical.map((s) => s.story_id)).toEqual(["a", "b"]);
  });

  it("does not mutate the array it is given", () => {
    const input = [story({ story_id: "b" }), story({ story_id: "a" })];
    sortStoriesForBrief(input);
    expect(input.map((s) => s.story_id)).toEqual(["b", "a"]);
  });

  it("survives a story with no usable timestamp", () => {
    const sorted = sortStoriesForBrief([story({ story_id: "junk", created_at: "not a date" })]);
    expect(sorted).toHaveLength(1);
    expect(getStoryPriority(sorted[0]).createdAt).toBe(0);
  });
});

describe("buildConsensusSummary", () => {
  it("names the publishers that line up on the story", () => {
    const summary = buildConsensusSummary(
      story({
        story_id: "1",
        sources: [
          { source: "dawn", count: 2 },
          { source: "geo", count: 1 },
        ],
      }),
    );
    expect(summary.agreed[0]).toContain("Dawn");
    expect(summary.agreed[0]).toContain("Geo");
  });

  it("says so plainly when only one publisher has it", () => {
    const summary = buildConsensusSummary(story({ story_id: "1" }));
    expect(summary.debated.join(" ")).toMatch(/single publisher/);
  });

  it("leads the debated column with what to watch when there is one", () => {
    const summary = buildConsensusSummary(
      story({ story_id: "1", metadata: { what_to_watch: "The IMF board vote on Friday" } }),
    );
    expect(summary.debated[0]).toBe("The IMF board vote on Friday.");
  });

  it("never returns more than three items in either column", () => {
    const summary = buildConsensusSummary(
      story({
        story_id: "1",
        impact_labels: ["💳 WALLET", "🚦 COMMUTE", "🛡️ SAFETY"],
        metadata: { story_tags: ["imf", "rupee", "inflation"], what_to_watch: "Watch." },
      }),
    );
    expect(summary.agreed.length).toBeLessThanOrEqual(3);
    expect(summary.debated.length).toBeLessThanOrEqual(3);
  });
});
