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
      latestPipelineRunAt: "2026-04-08T09:05:10Z",
    });

    render(await Home({ searchParams: Promise.resolve({ impact: "GOVERNANCE" }) }));

    expect(screen.getAllByText("No stories match this focus")).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: "Clear focus" })).toHaveLength(2);
    expect(screen.queryByText("Clear filters")).toBeNull();
  });
});
