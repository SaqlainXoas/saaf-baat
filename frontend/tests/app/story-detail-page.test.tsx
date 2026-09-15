import { render, screen } from "@testing-library/react";
import StoryDetail from "@/app/stories/[cluster_id]/page";
import { fetchStoryWithMeta } from "@/data/api";

jest.mock("@/data/api", () => ({
  fetchStoryWithMeta: jest.fn(),
}));

describe("Story detail page", () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  it("renders the original sources empty state when a live story has no article links", async () => {
    (fetchStoryWithMeta as jest.Mock).mockResolvedValue({
      story: {
        story_id: "story-1",
        created_at: "2026-04-08T06:00:00Z",
        headline: "Budget talks continue",
        snippet: "Officials say negotiations are still under way.",
        category: "governance",
        impact_labels: ["🏛️ GOVERNANCE"],
        sources: [{ source: "dawn", count: 1 }],
        metadata: {
          why_it_matters: "The outcome will shape the next fiscal package.",
          what_to_watch: "Watch for the next official briefing.",
        },
        articles: [],
      },
      status: "live",
      message: undefined,
      generatedAt: "2026-04-08T06:00:00Z",
      isFresh: true,
    });

    render(await StoryDetail({ params: Promise.resolve({ cluster_id: "story-1" }) }));

    // No `analysis` on this story, so the heading must not claim one.
    expect(screen.getByRole("heading", { name: "From the reporting" })).toBeDefined();
    expect(screen.queryByRole("heading", { name: "Analysis" })).toBeNull();
    expect(screen.getByText(/multi-source analysis is not available/i)).toBeDefined();
    expect(screen.queryByText("Quick brief")).toBeNull();
    expect(screen.queryByText("Top reporting")).toBeNull();
    expect(screen.getByText("Original sources")).toBeDefined();
    expect(screen.getAllByText(/not available for this story yet/i)).toHaveLength(1);
  });

  it("falls back to the existing snippet when analysis is unavailable", async () => {
    (fetchStoryWithMeta as jest.Mock).mockResolvedValue({
      story: {
        story_id: "story-1",
        created_at: "2026-04-08T06:00:00Z",
        headline: "Budget talks continue",
        snippet: "Officials say negotiations are still under way.",
        category: "governance",
        impact_labels: ["🏛️ GOVERNANCE"],
        sources: [{ source: "dawn", count: 1 }],
        metadata: {
          why_it_matters: "The outcome will shape the next fiscal package.",
          what_to_watch: "Watch for the next official briefing.",
        },
        articles: [],
      },
      status: "live",
      message: undefined,
      generatedAt: "2026-04-08T06:00:00Z",
      isFresh: true,
    });

    render(await StoryDetail({ params: Promise.resolve({ cluster_id: "story-1" }) }));

    expect(screen.getByText("Officials say negotiations are still under way.")).toBeDefined();
    expect(screen.getByText("Dawn")).toBeDefined();
    expect(screen.queryByRole("heading", { name: /the question/i })).toBeNull();
  });

  it("shows each original report once", async () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-04-08T08:00:00Z"));
    (fetchStoryWithMeta as jest.Mock).mockResolvedValue({
      story: {
        story_id: "story-1",
        created_at: "2026-04-08T06:00:00Z",
        headline: "Budget talks continue",
        snippet: "Officials say negotiations are still under way.",
        category: "governance",
        impact_labels: ["🏛️ GOVERNANCE"],
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
      generatedAt: "2026-04-08T06:00:00Z",
      isFresh: true,
    });

    render(await StoryDetail({ params: Promise.resolve({ cluster_id: "story-1" }) }));

    expect(screen.getByRole("link", { name: /back to brief/i })).toBeDefined();
    expect(screen.getAllByRole("link", { name: /finance ministry says talks continue/i })).toHaveLength(1);
    expect(screen.queryByText("Top reporting")).toBeNull();
  });

  it("gives the why-it-matters note the full width when there is no watch line", async () => {
    // what_to_watch is optional now - written only when the reporting names a
    // real next event - so a fixed two-column grid left the lone note at half
    // width beside an empty column.
    (fetchStoryWithMeta as jest.Mock).mockResolvedValue({
      story: {
        story_id: "petrol",
        created_at: "2026-08-27T06:00:00Z",
        headline: "Government cuts petrol and diesel prices",
        snippet: "Prices were cut overnight.",
        analysis: "The government reduced petrol by 50 paisa a litre.",
        category: "economy",
        impact_labels: ["\u{1F4B3} WALLET"],
        sources: [{ source: "dawn", count: 1 }],
        metadata: {
          why_it_matters: "Commuters pay 50 paisa less per litre starting today.",
        },
        articles: [],
      },
      status: "live",
      isFresh: true,
    });

    const { container } = render(
      await StoryDetail({ params: Promise.resolve({ cluster_id: "petrol" }) }),
    );

    expect(screen.getByRole("heading", { name: "Why it matters" })).toBeDefined();
    expect(screen.queryByRole("heading", { name: "What to watch" })).toBeNull();

    const note = container.querySelector(".sb-editorial-note");
    expect(note?.parentElement?.className).toContain("grid-cols-1");
    expect(note?.parentElement?.className).not.toContain("md:grid-cols-2");
  });

  it("renders a semantic question and labels contextual reports separately", async () => {
    (fetchStoryWithMeta as jest.Mock).mockResolvedValue({
      story: {
        story_id: "pims",
        created_at: "2026-08-27T06:00:00Z",
        headline: "Fourteen newborns die in PIMS nursery fire",
        snippet: "Fourteen newborns died after a nursery fire.",
        analysis: "Reports describe locked exits and conflicting accounts of the fire's cause.",
        question: "PIMS received Rs22 billion while emergency exits were reportedly locked. Which office was responsible for fire safety?",
        category: "health",
        impact_labels: ["🛡️ SAFETY"],
        sources: [{ source: "dawn", count: 1 }, { source: "brecorder", count: 1 }],
        metadata: {},
        articles: [],
        analysis_sources: [
          {
            id: "context-1",
            source: "nation",
            headline: "PIMS funding over three years",
            url: "https://example.com/context",
          },
        ],
      },
      status: "live",
      isFresh: true,
    });

    render(await StoryDetail({ params: Promise.resolve({ cluster_id: "pims" }) }));

    expect(screen.getByRole("heading", { name: "The question" })).toBeDefined();
    expect(screen.getByText(/Rs22 billion while emergency exits/i)).toBeDefined();
    expect(screen.getByRole("heading", { name: "Related reporting used for analysis" })).toBeDefined();
    expect(screen.getByText(/not counted as event corroboration/i)).toBeDefined();
    // The role is in the label, not only in the section heading above it.
    expect(screen.getByRole("link", { name: /Read The Nation context report/i })).toBeDefined();
    // A real analysis keeps the "Analysis" heading and no missing-analysis note.
    expect(screen.getByRole("heading", { name: "Analysis" })).toBeDefined();
    expect(screen.queryByText(/multi-source analysis is not available/i)).toBeNull();
  });

  it("keeps the product anchor back link even when the story detail is stale", async () => {
    (fetchStoryWithMeta as jest.Mock).mockResolvedValue({
      story: {
        story_id: "story-1",
        created_at: "2026-04-08T06:00:00Z",
        headline: "Budget talks continue",
        snippet: "Officials say negotiations are still under way.",
        category: "governance",
        impact_labels: ["🏛️ GOVERNANCE"],
        sources: [{ source: "dawn", count: 1 }],
        metadata: {
          why_it_matters: "The outcome will shape the next fiscal package.",
          what_to_watch: "Watch for the next official briefing.",
        },
        articles: [],
      },
      status: "live",
      message: undefined,
      generatedAt: "2026-04-08T06:00:00Z",
      isFresh: false,
    });

    render(await StoryDetail({ params: Promise.resolve({ cluster_id: "story-1" }) }));

    expect(screen.getByRole("link", { name: /back to brief/i })).toBeDefined();
  });

  it("throws on a live fetch failure so the static cache never stores the error", async () => {
    (fetchStoryWithMeta as jest.Mock).mockResolvedValue({
      story: null,
      status: "error-live-required",
      message: "Unable to load brief. Please try again shortly. (HTTP 503)",
    });

    await expect(
      StoryDetail({ params: Promise.resolve({ cluster_id: "lead-story" }) }),
    ).rejects.toThrow(/HTTP 503/);
  });

  it("keeps the unavailable-story recovery link keyboard focusable", async () => {
    (fetchStoryWithMeta as jest.Mock).mockResolvedValue({
      story: null,
      status: "not-found",
      message: undefined,
      generatedAt: undefined,
      isFresh: false,
    });

    render(await StoryDetail({ params: Promise.resolve({ cluster_id: "missing-story" }) }));

    const backLink = screen.getByRole("link", { name: /back to brief/i });
    expect(backLink.className).toContain("sb-focusable");
  });
});
