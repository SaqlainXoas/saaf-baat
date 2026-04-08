import { render, screen } from "@testing-library/react";
import TrustPreview from "@/components/TrustPreview";

const story = {
  story_id: "story-1",
  created_at: "2026-02-04T06:05:00Z",
  headline: "IMF Tranche Released: Rupee Strengthens",
  snippet: "State Bank confirms $1.2bn receipt.",
  category: "economy",
  impact_labels: ["💳 WALLET", "🏛️ GOVERNANCE"],
  confirmed_facts: [
    { text: "IMF", type: "ORG", sources: 3 },
    { text: "Pakistan", type: "GPE", sources: 3 },
  ],
  debated_claims: [{ text: "fuel cut", type: "MISC", sources: 2 }],
  sources: [
    { source: "dawn", count: 1 },
    { source: "tribune", count: 1 },
  ],
  metadata: {
    why_it_matters: "The release eases immediate default pressure.",
    what_to_watch: "Watch the inflation and reform timetable next.",
    story_tags: ["IMF", "Reserves", "Rupee"],
  },
};

describe("TrustPreview", () => {
  it("renders summary labels", () => {
    render(<TrustPreview story={story as any} />);
    expect(screen.getByText("Where reporting lines up")).toBeDefined();
    expect(screen.getByText("What to watch")).toBeDefined();
  });

  it("renders derived agreement summary", () => {
    render(<TrustPreview story={story as any} />);
    expect(screen.getByText(/Dawn and Tribune line up on the core development/i)).toBeDefined();
  });

  it("renders compact watch copy", () => {
    render(<TrustPreview story={story as any} layout="compact" />);
    expect(screen.getByText(/Watch:/)).toBeDefined();
    expect(screen.getByText(/inflation and reform timetable/i)).toBeDefined();
  });

  it("uses bounded headings and agreement wording for single-source stories", () => {
    render(
      <TrustPreview
        story={{
          ...story,
          sources: [{ source: "dawn", count: 1 }],
        } as any}
      />,
    );

    expect(screen.getByText("What’s clear in current reporting")).toBeDefined();
    expect(screen.getByText("What to watch")).toBeDefined();
    expect(screen.getByText(/Current reporting from Dawn points to the core development/i)).toBeDefined();
    expect(screen.queryByText("Where reporting lines up")).toBeNull();
  });

  it("drops noisy debated entities from compact copy", () => {
    render(
      <TrustPreview
        story={{
          ...story,
          debated_claims: [
            { text: "A week", type: "DATE", sources: 1 },
            { text: "April 3, 2026", type: "DATE", sources: 1 },
          ],
        } as any}
        layout="compact"
      />,
    );

    expect(screen.queryByText(/A week/i)).toBeNull();
    expect(screen.queryByText(/April 3, 2026/i)).toBeNull();
    expect(screen.getByText(/inflation and reform timetable/i)).toBeDefined();
  });
});
