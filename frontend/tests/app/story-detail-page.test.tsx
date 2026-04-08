import { render, screen } from "@testing-library/react";
import StoryDetail from "@/app/stories/[cluster_id]/page";
import { fetchStoryWithMeta } from "@/data/api";

jest.mock("@/data/api", () => ({
  fetchStoryWithMeta: jest.fn(),
}));

describe("Story detail page", () => {
  it("renders the original sources empty state when a live story has no article links", async () => {
    (fetchStoryWithMeta as jest.Mock).mockResolvedValue({
      story: {
        story_id: "story-1",
        created_at: "2026-04-08T06:00:00Z",
        headline: "Budget talks continue",
        snippet: "Officials say negotiations are still under way.",
        category: "governance",
        impact_labels: ["🏛️ GOVERNANCE"],
        confirmed_facts: [{ text: "Budget talks", type: "EVENT", sources: 1 }],
        debated_claims: [],
        sources: [{ source: "dawn", count: 1 }],
        metadata: {
          why_it_matters: "The outcome will shape the next fiscal package.",
          what_to_watch: "Watch for the next official briefing.",
        },
        articles: [],
      },
      status: "live",
      message: undefined,
      latestPipelineRunAt: "2026-04-08T06:00:00Z",
    });

    render(await StoryDetail({ params: Promise.resolve({ cluster_id: "story-1" }) }));

    expect(screen.getByText("Quick brief")).toBeDefined();
    expect(screen.getByText("Top reporting")).toBeDefined();
    expect(screen.getByText("Original sources")).toBeDefined();
    expect(screen.getAllByText(/not available for this story yet/i)).toHaveLength(2);
  });

  it("frames single-source stories honestly on the detail page", async () => {
    (fetchStoryWithMeta as jest.Mock).mockResolvedValue({
      story: {
        story_id: "story-1",
        created_at: "2026-04-08T06:00:00Z",
        headline: "Budget talks continue",
        snippet: "Officials say negotiations are still under way.",
        category: "governance",
        impact_labels: ["🏛️ GOVERNANCE"],
        confirmed_facts: [{ text: "Budget talks", type: "EVENT", sources: 1 }],
        debated_claims: [],
        sources: [{ source: "dawn", count: 1 }],
        metadata: {
          why_it_matters: "The outcome will shape the next fiscal package.",
          what_to_watch: "Watch for the next official briefing.",
        },
        articles: [],
      },
      status: "live",
      message: undefined,
      latestPipelineRunAt: "2026-04-08T06:00:00Z",
    });

    render(await StoryDetail({ params: Promise.resolve({ cluster_id: "story-1" }) }));

    expect(screen.getByText("Single-source reporting")).toBeDefined();
    expect(screen.getByText(/Current reporting is still anchored to Dawn alone/i)).toBeDefined();
    expect(screen.getByText("Reporting Summary")).toBeDefined();
  });

  it("surfaces top reporting links inside the quick brief", async () => {
    (fetchStoryWithMeta as jest.Mock).mockResolvedValue({
      story: {
        story_id: "story-1",
        created_at: "2026-04-08T06:00:00Z",
        headline: "Budget talks continue",
        snippet: "Officials say negotiations are still under way.",
        category: "governance",
        impact_labels: ["🏛️ GOVERNANCE"],
        confirmed_facts: [{ text: "Budget talks", type: "EVENT", sources: 2 }],
        debated_claims: [],
        sources: [
          { source: "dawn", count: 1 },
          { source: "geo", count: 1 },
        ],
        metadata: {
          why_it_matters: "The outcome will shape the next fiscal package.",
          what_to_watch: "Watch for the next official briefing.",
        },
        articles: [
          {
            id: "article-1",
            source: "dawn",
            headline: "Finance ministry says talks continue",
            url: "https://example.com/finance-talks",
            publish_date: "2026-04-08T05:30:00Z",
          },
        ],
      },
      status: "live",
      message: undefined,
      latestPipelineRunAt: "2026-04-08T06:00:00Z",
    });

    render(await StoryDetail({ params: Promise.resolve({ cluster_id: "story-1" }) }));

    expect(screen.getByRole("link", { name: /back to brief/i })).toBeDefined();
    expect(screen.getAllByRole("link", { name: /finance ministry says talks continue/i })).toHaveLength(2);
    expect(screen.getByText("Top reporting")).toBeDefined();
  });

  it("keeps the unavailable-story recovery link keyboard focusable", async () => {
    (fetchStoryWithMeta as jest.Mock).mockResolvedValue({
      story: null,
      status: "not-found",
      message: undefined,
      latestPipelineRunAt: undefined,
    });

    render(await StoryDetail({ params: Promise.resolve({ cluster_id: "missing-story" }) }));

    const backLink = screen.getByRole("link", { name: /back to brief/i });
    expect(backLink.className).toContain("sb-focusable");
  });
});
