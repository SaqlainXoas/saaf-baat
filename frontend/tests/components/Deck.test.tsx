import { render, screen, within } from "@testing-library/react";
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
    sources: [{ source: "dawn", count: 1 }],
    metadata: {
      what_to_watch: `Watch item ${id}`,
    },
  };
}

describe("Deck", () => {
  const stories = [story("1"), story("2"), story("3"), story("4")];

  it("shows how far through the finite brief the reader is", () => {
    render(<Deck stories={stories} />);
    expect(screen.getByText("1 / 4")).toBeDefined();
    expect(screen.getByText("Story 1 of 4")).toBeDefined();
  });

  it("numbers every card so the rank is the order", () => {
    // The "Top story" / "Next up" / "Then worth your time" headings are gone:
    // with a numbered deck the rank is the order, and the headings asked the
    // "am I done yet?" question the counter answers.
    render(<Deck stories={stories} />);

    expect(screen.queryByText("Top story")).toBeNull();
    expect(screen.queryByText("Next up")).toBeNull();
    expect(screen.queryByText("Then worth your time")).toBeNull();
    ["1", "2", "3", "4"].forEach((rank) => {
      expect(screen.getByText(rank)).toBeDefined();
    });
  });

  it("renders every story in ranked order with its detail link", () => {
    render(<Deck stories={stories} />);
    ["1", "2", "3", "4"].forEach((id) => {
      expect(
        screen.getByRole("link", { name: new RegExp(`Headline ${id}`, "i") }).getAttribute("href"),
      ).toBe(`/stories/${id}`);
    });
    const leadLink = screen.getByRole("link", { name: /Headline 1/i });
    expect(within(leadLink).getByText("What to watch:")).toBeDefined();
    expect(within(leadLink).getByText("Watch item 1")).toBeDefined();
  });

  it("snaps by proximity, never mandatory", () => {
    // A reader skims a brief and skips what they already know. Twelve
    // mandatory full-screen stops would make it slower than a plain list.
    const { container } = render(<Deck stories={stories} />);

    const deck = container.querySelector(".sb-deck");
    expect(deck).not.toBeNull();
    expect(container.querySelectorAll(".sb-deck-item")).toHaveLength(4);
  });

  it("gives the lead card its own weight", () => {
    const { container } = render(<Deck stories={stories} />);
    expect(container.querySelectorAll(".sb-deck-item-lead")).toHaveLength(1);
    expect(container.querySelectorAll(".sb-story-card-lead")).toHaveLength(1);
    expect(container.querySelectorAll(".sb-story-card-supporting")).toHaveLength(3);
  });

  it("shows the finite-end copy", () => {
    render(<Deck stories={stories} />);
    expect(screen.getByText(/You're all caught up/)).toBeDefined();
    expect(screen.getByText(/ends here on purpose/)).toBeDefined();
  });

  it("keeps all story links keyboard-focusable", () => {
    render(<Deck stories={stories} />);

    screen.getAllByRole("link").forEach((link) => {
      expect(link.className).toContain("sb-focusable");
    });
  });

  it("uses latest-brief language when the mobile deck is showing a stale brief", () => {
    render(
      <Deck
        stories={stories}
        generatedAt="2026-05-10T22:30:00Z"
        isFresh={false}
      />,
    );

    expect(screen.getByText("Latest brief")).toBeDefined();
    expect(screen.queryByText("Today's brief")).toBeNull();
  });
});
