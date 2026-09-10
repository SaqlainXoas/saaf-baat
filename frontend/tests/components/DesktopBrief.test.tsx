import { render, screen, within } from "@testing-library/react";
import DesktopBrief from "@/components/DesktopBrief";
import type { StoryCardData } from "@/data/types";

jest.mock("@/components/BrandHeader", () => {
  const MockBrandHeader = () => <div>Brand Header</div>;
  return MockBrandHeader;
});
jest.mock("@/components/DataStatusBanner", () => {
  const MockDataStatusBanner = () => <div>Data Banner</div>;
  return MockDataStatusBanner;
});

function story(id: string): StoryCardData {
  return {
    story_id: id,
    created_at: "2026-02-01T00:00:00Z",
    headline: `Headline ${id}`,
    snippet: `Snippet ${id}`,
    category: "economy",
    impact_labels: ["💳 WALLET"],
    sources: [{ source: "dawn", count: 1 }],
  };
}

describe("DesktopBrief", () => {
  const stories = [story("1"), story("2"), story("3"), story("4")];

  it("renders the first story as the lead item in the vertical flow", () => {
    render(<DesktopBrief stories={stories} status="live" />);

    const firstStory = screen.getByTestId("desktop-story-1");
    expect(within(firstStory).getByText("Headline 1")).toBeDefined();
    expect(firstStory.getAttribute("href")).toBe("/stories/1");
  });

  it("renders all stories in a single ordered flow", () => {
    render(<DesktopBrief stories={stories} status="live" />);
    expect(screen.getByTestId("desktop-story-2")).toBeDefined();
    expect(screen.getByTestId("desktop-story-3")).toBeDefined();
    expect(screen.getByTestId("desktop-story-4")).toBeDefined();
  });

  it("does not render homepage section headings", () => {
    render(<DesktopBrief stories={stories} status="live" />);
    expect(screen.queryByText("Top of the brief")).toBeNull();
    expect(screen.queryByText("More to know")).toBeNull();
  });

  it("numbers every story, the way mobile does", () => {
    // Desktop rendered twelve identical rows with no rank at all while mobile
    // carried numerals - the wider screen showed strictly less than the phone.
    const { container } = render(
      <DesktopBrief stories={stories} status="live" />,
    );
    const ranks = Array.from(container.querySelectorAll(".sb-deck-rank-number")).map(
      (node) => node.textContent,
    );
    expect(ranks).toEqual(["1", "2", "3", "4"]);
  });

  it("distinguishes the lead story from the rest", () => {
    const { container } = render(
      <DesktopBrief stories={stories} status="live" />,
    );
    expect(container.querySelectorAll(".sb-story-card-lead")).toHaveLength(1);
    expect(container.querySelectorAll(".sb-story-card-supporting")).toHaveLength(3);
  });

  it("shows how far through the finite brief the reader is", () => {
    render(<DesktopBrief stories={stories} status="live" />);
    expect(screen.getByText("1 / 4")).toBeDefined();
    expect(screen.getByText("Story 1 of 4")).toBeDefined();
  });

  it("ends the brief on purpose", () => {
    render(<DesktopBrief stories={stories} status="live" />);
    expect(screen.getByText(/You’re all caught up/)).toBeDefined();
    expect(screen.getByText(/ends here on purpose/)).toBeDefined();
  });

  it("renders nothing at all when there are no stories", () => {
    const { container } = render(
      <DesktopBrief stories={[]} status="live" />,
    );
    expect(container.firstChild).toBeNull();
  });
});
