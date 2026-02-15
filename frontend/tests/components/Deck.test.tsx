import { fireEvent, render, screen } from "@testing-library/react";
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
  const stories = [story("1"), story("2"), story("3")];

  it("renders progress counter", () => {
    render(<Deck stories={stories} />);
    expect(screen.getByText("1 / 3")).toBeDefined();
  });

  it("switches cards when dot is clicked", () => {
    render(<Deck stories={stories} />);
    fireEvent.click(screen.getByLabelText("Go to story 2"));
    expect(screen.getByText("2 / 3")).toBeDefined();
  });

  it("shows caught-up copy on the last card", () => {
    render(<Deck stories={stories} />);
    fireEvent.click(screen.getByLabelText("Go to story 3"));
    expect(screen.getByText(/You're all caught up/)).toBeDefined();
    expect(screen.getByText(/Enjoy your day/)).toBeDefined();
  });
});
