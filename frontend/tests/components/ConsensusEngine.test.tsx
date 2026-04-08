import { render, screen } from "@testing-library/react";
import ConsensusEngine from "@/components/ConsensusEngine";

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
  debated_claims: [{ text: "Long-term inflation impact", type: "MISC", sources: 2 }],
  sources: [
    { source: "dawn", count: 1 },
    { source: "tribune", count: 1 },
  ],
  metadata: {
    why_it_matters: "The release eases immediate default pressure.",
    what_to_watch: "Watch the inflation and reform timetable next.",
    story_tags: ["IMF", "Reserves", "Rupee"],
  },
  articles: [],
};

describe("ConsensusEngine", () => {
  it("renders section heading", () => {
    render(<ConsensusEngine story={story as any} />);
    expect(screen.getByText("Consensus Summary")).toBeDefined();
  });

  it("renders What's agreed block", () => {
    render(<ConsensusEngine story={story as any} />);
    expect(screen.getByText(/where reporting lines up/i)).toBeDefined();
  });

  it("renders What's debated block", () => {
    render(<ConsensusEngine story={story as any} />);
    expect(screen.getByText(/what to watch/i)).toBeDefined();
  });

  it("renders derived summary bullets", () => {
    render(<ConsensusEngine story={story as any} />);
    expect(screen.getByText(/Dawn and Tribune line up on the core development/i)).toBeDefined();
    expect(screen.getByText(/Watch the inflation and reform timetable next/i)).toBeDefined();
  });

  it("uses bounded section headings for a single-source story", () => {
    render(
      <ConsensusEngine
        story={{
          ...story,
          sources: [{ source: "dawn", count: 1 }],
        } as any}
      />,
    );

    expect(screen.getByText("What’s clear in current reporting")).toBeDefined();
    expect(screen.getByText("What to Watch")).toBeDefined();
    expect(screen.getByText(/Current reporting from Dawn points to the core development/i)).toBeDefined();
  });

  it("does not turn noisy debated dates into user-facing bullets", () => {
    render(
      <ConsensusEngine
        story={{
          ...story,
          debated_claims: [
            { text: "A week", type: "DATE", sources: 1 },
            { text: "April 3, 2026", type: "DATE", sources: 1 },
          ],
        } as any}
      />,
    );

    expect(screen.queryByText(/A week/i)).toBeNull();
    expect(screen.queryByText(/April 3, 2026/i)).toBeNull();
    expect(screen.getByText(/Watch the inflation and reform timetable next/i)).toBeDefined();
  });
});
