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
  metadata: {
    why_it_matters: "Household costs and market confidence can shift quickly.",
    what_to_watch: "Watch for the next official announcement.",
  },
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

  it("renders a watch note in default variant", () => {
    render(<StoryCard story={mockStory} />);
    expect(screen.getByText("What to watch")).toBeDefined();
    expect(screen.getByText("Watch for the next official announcement.")).toBeDefined();
  });

  it("renders a lighter featured card treatment", () => {
    render(<StoryCard story={mockStory} variant="featured" />);
    expect(screen.queryByText("Household costs and market confidence can shift quickly.")).toBeNull();
    expect(screen.queryByText("Economy")).toBeNull();
    expect(screen.queryByText(/Sources assessed:/)).toBeNull();
  });

  it("renders the homepage variant without rank dots or extra chrome", () => {
    render(<StoryCard story={mockStory} variant="homepage" />);
    expect(screen.queryByText("Economy")).toBeNull();
    expect(screen.queryByText(/Sources assessed:/)).toBeNull();
    expect(screen.queryByText("1")).toBeNull();
  });

  it("uses compact snippet clamp styling in compact variant", () => {
    render(<StoryCard story={mockStory} variant="compact" />);
    expect(screen.getByText("State Bank confirms $1.2bn receipt.").className).toContain("sb-clamp-2");
  });

  it("keeps the default variant richer than homepage cards", () => {
    render(<StoryCard story={mockStory} />);
    expect(screen.getByText("Economy")).toBeDefined();
    expect(screen.getByText(/Sources assessed:/)).toBeDefined();
  });
});
