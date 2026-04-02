import { fireEvent, render, screen, within } from "@testing-library/react";
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
  const stories = [story("1"), story("2"), story("3")];

  it("shows first story in featured preview by default", () => {
    render(<DesktopBrief stories={stories} availableSources={["dawn"]} status="live" />);

    const featured = screen.getByTestId("desktop-featured-preview");
    expect(within(featured).getByText("Headline 1")).toBeDefined();
    expect(within(featured).getByRole("link").getAttribute("href")).toBe("/stories/1");
  });

  it("does not duplicate active featured story inside compact list", () => {
    render(<DesktopBrief stories={stories} availableSources={["dawn"]} status="live" />);
    expect(screen.queryByTestId("desktop-compact-1")).toBeNull();
    expect(screen.getByTestId("desktop-compact-2")).toBeDefined();
    expect(screen.getByTestId("desktop-compact-3")).toBeDefined();
  });

  it("updates featured preview on compact card hover", () => {
    render(<DesktopBrief stories={stories} availableSources={["dawn"]} status="live" />);

    fireEvent.mouseEnter(screen.getByTestId("desktop-compact-2"));
    const featured = screen.getByTestId("desktop-featured-preview");
    expect(within(featured).getByText("Headline 2")).toBeDefined();
    expect(within(featured).getByRole("link").getAttribute("href")).toBe("/stories/2");
  });

  it("resets featured preview to first story after hover-out", () => {
    render(<DesktopBrief stories={stories} availableSources={["dawn"]} status="live" />);

    fireEvent.mouseEnter(screen.getByTestId("desktop-compact-3"));
    fireEvent.mouseLeave(screen.getByTestId("desktop-compact-list"));

    const featured = screen.getByTestId("desktop-featured-preview");
    expect(within(featured).getByText("Headline 1")).toBeDefined();
    expect(within(featured).getByRole("link").getAttribute("href")).toBe("/stories/1");
  });

  it("updates featured preview on keyboard focus", () => {
    render(<DesktopBrief stories={stories} availableSources={["dawn"]} status="live" />);

    fireEvent.focus(screen.getByTestId("desktop-compact-3"));
    const featured = screen.getByTestId("desktop-featured-preview");
    expect(within(featured).getByText("Headline 3")).toBeDefined();
    expect(within(featured).getByRole("link").getAttribute("href")).toBe("/stories/3");
  });
});
