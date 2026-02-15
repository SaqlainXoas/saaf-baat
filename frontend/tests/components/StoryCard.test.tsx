import { render, screen } from "@testing-library/react";
import StoryCard from "@/components/StoryCard";

// next/link renders as <a> in test env via next/jest
const mockStory = {
  story_id: "test-123",
  created_at: "2026-02-04T06:05:00Z",
  headline: "IMF Tranche Released: Rupee Strengthens",
  snippet: "State Bank confirms $1.2bn receipt.",
  category: "economy",
  impact_labels: ["💳 WALLET", "🏛️ GOVERNANCE"],
  confirmed_facts: [
    { text: "IMF", type: "ORG", sources: 3 },
    { text: "Pakistan", type: "GPE", sources: 3 },
  ],
  debated_claims: [{ text: "fuel cut", type: "MISC", sources: 1 }],
  sources: [
    { source: "dawn", count: 1 },
    { source: "geo", count: 1 },
    { source: "tribune", count: 1 },
  ],
};

describe("StoryCard", () => {
  it("renders headline", () => {
    render(<StoryCard story={mockStory} />);
    expect(screen.getByText("IMF Tranche Released: Rupee Strengthens")).toBeDefined();
  });

  it("renders snippet", () => {
    render(<StoryCard story={mockStory} />);
    expect(screen.getByText("State Bank confirms $1.2bn receipt.")).toBeDefined();
  });

  it("renders impact pill label", () => {
    render(<StoryCard story={mockStory} />);
    expect(screen.getByText("WALLET")).toBeDefined();
  });

  it("renders source names capitalised", () => {
    render(<StoryCard story={mockStory} />);
    expect(screen.getByText(/Dawn.*Geo.*Tribune/)).toBeDefined();
  });

  it("shows Open → when not background", () => {
    render(<StoryCard story={mockStory} />);
    expect(screen.getByText("Open →")).toBeDefined();
  });

  it("hides Open → when isBackground", () => {
    render(<StoryCard story={mockStory} isBackground />);
    expect(screen.queryByText("Open →")).toBeNull();
  });

  it("renders trust preview chips", () => {
    render(<StoryCard story={mockStory} />);
    expect(screen.getByText("IMF")).toBeDefined();
    expect(screen.getByText("fuel cut")).toBeDefined();
  });

  it("uses compact snippet clamp styling in compact variant", () => {
    render(<StoryCard story={mockStory} variant="compact" />);
    expect(screen.getByText("State Bank confirms $1.2bn receipt.").className).toContain("sb-clamp-1");
  });
});
