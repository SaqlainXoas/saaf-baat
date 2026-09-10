jest.mock("@/components/BrandHeader", () => ({ __esModule: true, default: () => <header>Saaf Baat</header> }));
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
  it("shows a simple empty edition without filter recovery controls", async () => {
    (fetchFeedWithMeta as jest.Mock).mockResolvedValue({
      stories: [],
      status: "live",
      message: undefined,
      generatedAt: "2026-04-08T09:05:10Z",
      isFresh: true,
    });

    render(await Home());

    expect(screen.getAllByText("The morning brief is being prepared")).toHaveLength(2);
    expect(screen.queryByRole("link", { name: "Clear focus" })).toBeNull();
    expect(screen.queryByText("Clear filters")).toBeNull();
  });

  it("renders a card the backend published even if its impact line is thin", async () => {
    (fetchFeedWithMeta as jest.Mock).mockResolvedValue({
      stories: [
        {
          story_id: "story-1",
          created_at: "2026-05-12T01:00:00Z",
          headline: "Incomplete card",
          snippet: "The API guarantees why_it_matters, so this card still renders.",
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

    render(await Home());

    // I-7: a client-side filter over a backend contract gap silently shrank
    // the brief. The guarantee lives in the API now, so what the backend
    // published is what the reader sees.
    expect(screen.queryByText("The morning brief is being prepared")).toBeNull();
    expect(screen.getByText("DesktopBrief")).toBeDefined();
    expect(screen.getByText("Deck")).toBeDefined();
  });

  it("shows the live failure message when the API request fails", async () => {
    (fetchFeedWithMeta as jest.Mock).mockResolvedValue({
      stories: [],
      status: "error-live-required",
      message: "Unable to load brief. Please try again shortly.",
      generatedAt: undefined,
      isFresh: false,
    });

    render(await Home());

    expect(screen.getAllByText("Unable to load brief")).toHaveLength(2);
    expect(screen.getAllByText("Unable to load brief. Please try again shortly.")).toHaveLength(2);
  });
});

describe("breakpoint layout contract", () => {
  beforeEach(() => {
    (fetchFeedWithMeta as jest.Mock).mockResolvedValue({
      stories: [
        {
          story_id: "1",
          created_at: "2026-08-25T06:00:00Z",
          headline: "Headline",
          snippet: "Snippet.",
          category: "economy",
          impact_labels: ["\ud83d\udcb3 WALLET"],
          sources: [{ source: "dawn", count: 1 }],
          metadata: { why_it_matters: "It costs more." },
        },
      ],
      status: "live",
      message: undefined,
      generatedAt: "2026-08-25T06:00:00Z",
      isFresh: true,
    });
  });

  it("hands tablets the column layout, not the phone deck", async () => {
    // This was `lg:` (1024px), which rendered the phone deck inside a 416px
    // max-w-md column in a 768px viewport - most of a tablet screen empty
    // either side. The two classes must stay complementary: any gap or
    // overlap means a width that shows both layouts or neither.
    const { container } = render(await Home());
    const desktop = container.querySelector('[class*="md:block"]');
    const phone = container.querySelector('[class*="md:hidden"]');

    expect(desktop?.className).toContain("hidden");
    expect(desktop?.className).toContain("md:block");
    expect(phone?.className).toContain("md:hidden");
    expect(desktop?.className).not.toContain("lg:");
    expect(phone?.className).not.toContain("lg:");
  });

  it("renders both layouts so neither depends on client-side width detection", async () => {
    const { container } = render(await Home());
    expect(container.querySelector('[class*="md:block"]')).not.toBeNull();
    expect(container.querySelector('[class*="md:hidden"]')).not.toBeNull();
  });
});
