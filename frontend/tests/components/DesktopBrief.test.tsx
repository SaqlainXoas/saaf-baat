import { render, screen, within } from "@testing-library/react";
import DesktopBrief from "@/components/DesktopBrief";
import type { StoryCardData } from "@/data/types";

jest.mock("@/components/BrandHeader", () => () => <div>Brand Header</div>);
jest.mock("@/components/DataStatusBanner", () => () => <div>Data Banner</div>);

function story(id: string): StoryCardData {
  return {
    story_id: id,
    created_at: "2026-02-01T00:00:00Z",
    headline: `Headline ${id}`,
    snippet: `Snippet ${id}`,
    category: "economy",
    impact_labels: ["💳 WALLET"],
    confirmed_facts: [{ text: `Fact ${id}`, type: "ORG", sources: 2 }],
    debated_claims: [{ text: `Debated ${id}`, type: "MISC", sources: 1 }],
    sources: [{ source: "dawn", count: 1 }],
  };
}

describe("DesktopBrief", () => {
  const stories = [story("1"), story("2"), story("3"), story("4")];

  it("shows first story as the lead story", () => {
    render(<DesktopBrief stories={stories} availableSources={["dawn"]} status="live" />);

    const featured = screen.getByTestId("desktop-featured-preview");
    expect(within(featured).getByText("Headline 1")).toBeDefined();
    expect(featured.getAttribute("href")).toBe("/stories/1");
  });

  it("renders sidebar stories separately from the lead", () => {
    render(<DesktopBrief stories={stories} availableSources={["dawn"]} status="live" />);
    expect(screen.getByTestId("desktop-sidebar-2")).toBeDefined();
    expect(screen.getByTestId("desktop-sidebar-3")).toBeDefined();
  });

  it("renders lower grid stories when enough stories are present", () => {
    render(<DesktopBrief stories={stories} availableSources={["dawn"]} status="live" />);
    expect(screen.getByTestId("desktop-grid-4")).toBeDefined();
  });
});
