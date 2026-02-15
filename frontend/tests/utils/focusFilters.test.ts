import type { StoryCardData } from "@/data/types";
import { applyFilters, deriveAvailableSources, parseFilters, serialiseFilters } from "@/utils/focusFilters";

function story(partial: Partial<StoryCardData>): StoryCardData {
  return {
    story_id: "s",
    created_at: "2026-02-01T00:00:00Z",
    headline: "h",
    snippet: "sn",
    category: "c",
    impact_labels: ["💳 WALLET"],
    confirmed_facts: [],
    debated_claims: [],
    sources: [{ source: "dawn", count: 1 }],
    ...partial,
  };
}

describe("focusFilters", () => {
  it("parses filters from URLSearchParams", () => {
    const filters = parseFilters(new URLSearchParams("impact=wallet,SAFETY&sources=Dawn,geo"));
    expect(Array.from(filters.impacts).sort()).toEqual(["SAFETY", "WALLET"]);
    expect(Array.from(filters.sources).sort()).toEqual(["dawn", "geo"]);
  });

  it("serialises filters back to query values", () => {
    const f = parseFilters(new URLSearchParams("impact=WALLET&sources=dawn,geo"));
    const s = serialiseFilters(f);
    expect(s.impact).toBe("WALLET");
    expect(s.sources).toBe("dawn,geo");
  });

  it("filters stories by primary impact label and sources (OR within each group)", () => {
    const stories = [
      story({ story_id: "a", impact_labels: ["💳 WALLET"], sources: [{ source: "dawn", count: 1 }] }),
      story({ story_id: "b", impact_labels: ["🛡️ SAFETY"], sources: [{ source: "geo", count: 1 }] }),
      story({ story_id: "c", impact_labels: ["🏛️ GOVERNANCE"], sources: [{ source: "tribune", count: 1 }] }),
    ];

    const filters = parseFilters(new URLSearchParams("impact=WALLET,SAFETY&sources=geo"));
    const out = applyFilters(stories, filters);
    expect(out.map((s) => s.story_id)).toEqual(["b"]);
  });

  it("derives available sources with stable ordering", () => {
    const stories = [
      story({ sources: [{ source: "tribune", count: 1 }] }),
      story({ sources: [{ source: "dawn", count: 1 }] }),
      story({ sources: [{ source: "geo", count: 1 }] }),
      story({ sources: [{ source: "other", count: 1 }] }),
    ];
    expect(deriveAvailableSources(stories)).toEqual(["dawn", "geo", "tribune", "other"]);
  });
});

