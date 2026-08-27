import { render, screen } from "@testing-library/react";
import StoryCard from "@/components/StoryCard";
import type { StoryCardData } from "@/data/types";

const mockStory: StoryCardData = {
  story_id: "test-123",
  created_at: "2026-02-04T06:05:00Z",
  headline: "IMF Tranche Released: Rupee Strengthens",
  snippet: "State Bank confirms $1.2bn receipt.",
  category: "economy",
  impact_labels: ["💳 WALLET", "🏛️ GOVERNANCE"],
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
  it("renders headline, snippet and impact pill", () => {
    render(<StoryCard story={mockStory} />);
    expect(screen.getByText("IMF Tranche Released: Rupee Strengthens")).toBeDefined();
    expect(screen.getByText("State Bank confirms $1.2bn receipt.")).toBeDefined();
    expect(screen.getByText("WALLET")).toBeDefined();
  });

  it("renders source names capitalised", () => {
    render(<StoryCard story={mockStory} />);
    expect(screen.getByText(/Dawn.*Geo.*Tribune/)).toBeDefined();
  });

  it("shows Open → only when it is a real link target", () => {
    const { unmount } = render(<StoryCard story={mockStory} />);
    expect(screen.getByText("Open →")).toBeDefined();
    unmount();

    render(<StoryCard story={mockStory} isBackground />);
    expect(screen.queryByText("Open →")).toBeNull();
  });

  it("renders the impact line on both variants", () => {
    // "Why it matters" is the middle third of the product promise. It used to
    // be read from metadata and then rendered nowhere a reader could see it -
    // only in a `default` variant that neither surface used.
    for (const variant of ["lead", "supporting"] as const) {
      const { unmount } = render(<StoryCard story={mockStory} variant={variant} />);
      expect(
        screen.getByText("Household costs and market confidence can shift quickly."),
      ).toBeDefined();
      unmount();
    }
  });

  it("puts the impact line above the snippet", () => {
    // Order is the point: headline, then what it means for you, then detail.
    const { container } = render(<StoryCard story={mockStory} variant="lead" />);
    const impact = container.querySelector(".sb-impact-line");
    const snippet = container.querySelector(".sb-snippet-lead");
    expect(impact).not.toBeNull();
    expect(snippet).not.toBeNull();
    expect(impact!.compareDocumentPosition(snippet!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("renders the watch line on both variants", () => {
    render(<StoryCard story={mockStory} variant="supporting" />);
    expect(screen.getByText("What to watch:")).toBeDefined();
    expect(screen.getByText(/Watch for the next official announcement/)).toBeDefined();
  });

  it("gives the lead card its own treatment", () => {
    const { container, unmount } = render(<StoryCard story={mockStory} variant="lead" />);
    expect(container.querySelector(".sb-story-card-lead")).not.toBeNull();
    expect(container.querySelector(".sb-headline-lead")).not.toBeNull();
    unmount();

    const supporting = render(<StoryCard story={mockStory} variant="supporting" />);
    expect(supporting.container.querySelector(".sb-story-card-supporting")).not.toBeNull();
    expect(supporting.container.querySelector(".sb-story-card-lead")).toBeNull();
  });

  it("omits the impact line rather than rendering an empty paragraph", () => {
    const bare = { ...mockStory, metadata: {} };
    const { container } = render(<StoryCard story={bare} />);
    expect(container.querySelector(".sb-impact-line")).toBeNull();
    expect(screen.queryByText("What to watch:")).toBeNull();
  });

  it("names a single source rather than saying '1 sources'", () => {
    const single = { ...mockStory, sources: [{ source: "dawn", count: 1 }] };
    render(<StoryCard story={single} />);
    expect(screen.getByText("Dawn")).toBeDefined();
  });

  it("collapses four or more sources into a count", () => {
    const many = {
      ...mockStory,
      sources: ["dawn", "geo", "tribune", "ary"].map((source) => ({ source, count: 1 })),
    };
    render(<StoryCard story={many} />);
    expect(screen.getByText("4 sources")).toBeDefined();
  });
});
