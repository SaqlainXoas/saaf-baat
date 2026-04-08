import { render, screen } from "@testing-library/react";
import Deck from "@/components/Deck";
import type { StoryCardData } from "@/data/types";

function story(id: string): StoryCardData {
  return {
    story_id: id,
    created_at: "2026-02-01T00:00:00Z",
    headline: `Headline ${id}`,
    snippet: `Snippet ${id}`,
    category: "economy",
    impact_labels: ["💳 WALLET"],
    confirmed_facts: [{ text: `Fact ${id}`, type: "ORG", sources: 2 }],
    debated_claims: [],
    sources: [{ source: "dawn", count: 1 }],
  };
}

describe("Deck", () => {
  const stories = [story("1"), story("2"), story("3"), story("4")];

  it("renders the story count summary", () => {
    render(<Deck stories={stories} />);
    expect(screen.getByText("4 stories")).toBeDefined();
  });

  it("renders the first story as the lead story", () => {
    render(<Deck stories={stories} />);
    expect(screen.getByText("Lead story")).toBeDefined();
    expect(screen.getByRole("link", { name: /Headline 1/i }).getAttribute("href")).toBe("/stories/1");
  });

  it("renders supporting stories in ranked order", () => {
    render(<Deck stories={stories} />);
    expect(screen.getByText("Also moving")).toBeDefined();
    expect(screen.getByRole("link", { name: /Headline 2/i }).getAttribute("href")).toBe("/stories/2");
    expect(screen.getByRole("link", { name: /Headline 3/i }).getAttribute("href")).toBe("/stories/3");
    expect(screen.getByText("Then worth your time")).toBeDefined();
    expect(screen.getByRole("link", { name: /Headline 4/i }).getAttribute("href")).toBe("/stories/4");
  });

  it("shows the finite-end copy", () => {
    render(<Deck stories={stories} />);
    expect(screen.getByText(/You're all caught up/)).toBeDefined();
    expect(screen.getByText(/The brief ends here on purpose/)).toBeDefined();
  });

  it("keeps all story links keyboard-focusable", () => {
    render(<Deck stories={stories} />);

    screen.getAllByRole("link").forEach((link) => {
      expect(link.className).toContain("sb-focusable");
    });
  });
});
