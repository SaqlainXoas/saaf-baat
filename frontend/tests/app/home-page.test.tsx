import { render, screen } from "@testing-library/react";
import Home from "@/app/page";
import { fetchFeedWithMeta } from "@/data/api";

jest.mock("@/data/api", () => ({
  fetchFeedWithMeta: jest.fn(),
}));

jest.mock("@/components/MorningGreeting", () => function MorningGreetingMock() {
  return <div>MorningGreeting</div>;
});

jest.mock("@/components/DesktopBrief", () => function DesktopBriefMock() {
  return <div>DesktopBrief</div>;
});

jest.mock("@/components/Deck", () => function DeckMock() {
  return <div>Deck</div>;
});

jest.mock("@/components/DataStatusBanner", () => function DataStatusBannerMock() {
  return <div>DataStatusBanner</div>;
});

describe("Home page", () => {
  it("uses the product's focus language in the filtered empty state", async () => {
    (fetchFeedWithMeta as jest.Mock).mockResolvedValue({
      stories: [],
      status: "live",
      message: undefined,
      generatedAt: "2026-04-08T09:05:10Z",
      isFresh: true,
    });

    render(await Home({ searchParams: Promise.resolve({ impact: "GOVERNANCE" }) }));

    expect(screen.getAllByText("No stories match this focus")).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: "Clear focus" })).toHaveLength(2);
    expect(screen.queryByText("Clear filters")).toBeNull();
  });

  it("does not render homepage cards that are missing an impact line", async () => {
    (fetchFeedWithMeta as jest.Mock).mockResolvedValue({
      stories: [
        {
          story_id: "story-1",
          created_at: "2026-05-12T01:00:00Z",
          headline: "Incomplete card",
          snippet: "Missing impact line should keep this off the homepage.",
          category: "economy",
          impact_labels: ["💳 WALLET"],
          sources: [{ source: "dawn", count: 1 }],
          metadata: {},
        },
      ],
      status: "live",
      message: undefined,
      generatedAt: "2026-05-12T01:00:00Z",
      isFresh: true,
    });

    render(await Home({ searchParams: Promise.resolve({}) }));

    expect(screen.getAllByText("Today's brief is being prepared")).toHaveLength(2);
    expect(screen.queryByText("DesktopBrief")).toBeNull();
  });

  it("shows the live failure message when the API request fails", async () => {
    (fetchFeedWithMeta as jest.Mock).mockResolvedValue({
      stories: [],
      status: "error-live-required",
      message: "Unable to load brief. Please try again shortly.",
      generatedAt: undefined,
      isFresh: false,
    });

    render(await Home({ searchParams: Promise.resolve({}) }));

    expect(screen.getAllByText("Unable to load brief")).toHaveLength(2);
    expect(screen.getAllByText("Unable to load brief. Please try again shortly.")).toHaveLength(2);
  });
});
