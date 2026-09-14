import { render, screen, within } from "@testing-library/react";
import MorningGreeting from "@/components/MorningGreeting";

describe("MorningGreeting", () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  it("opens with the greeting", () => {
    // The greeting is the thing this product opens with, and it was missing
    // from the code entirely - the header led with "Back to brief · <date>".
    render(<MorningGreeting storyCount={5} />);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(within(heading).getByTitle("Good morning").textContent).toBe("Subah Bakhair");
  });

  it("ships all three time bands and lets CSS choose", () => {
    // The masthead is time-aware on the Karachi clock, but the page is served
    // from Vercel's cache, so the band cannot be chosen at render time. React
    // emits all three; the inline script's data-pkt-band reveals one. Rendered
    // at 16:00 PKT the markup must still be identical to any other hour.
    jest.useFakeTimers().setSystemTime(new Date("2026-05-10T11:00:00Z"));
    render(<MorningGreeting storyCount={5} />);
    const heading = screen.getByRole("heading", { level: 1 });

    expect(heading.querySelectorAll("[data-band]")).toHaveLength(3);
    expect(within(heading).getByTitle("Today's word").textContent).toBe("Aaj Ki Baat");
    expect(within(heading).getByTitle("Good evening").textContent).toBe("Shaam Bakhair");
  });

  it("says where and when, once", () => {
    render(<MorningGreeting storyCount={5} />);
    expect(screen.getAllByText(/Pakistan/).length).toBe(1);
  });

  it("states the story count", () => {
    render(<MorningGreeting storyCount={7} />);
    expect(screen.getByText(/7 essential stories/)).toBeDefined();
  });

  it("does not render fake weather", () => {
    render(<MorningGreeting storyCount={5} />);
    expect(screen.queryByText(/°C/)).toBeNull();
  });

  it("renders a real edition date instead of a placeholder label", () => {
    render(<MorningGreeting storyCount={5} />);
    expect(screen.queryByText(/^Today$/)).toBeNull();
    expect(screen.getByText(/[A-Z][a-z]{2}, \d{1,2} [A-Z][a-z]{2}/)).toBeDefined();
  });

  it("shows the brief's own date when the brief is stale", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-05-12T08:00:00Z"));
    render(<MorningGreeting storyCount={5} generatedAt="2026-05-10T22:30:00Z" isFresh={false} />);
    expect(screen.getByText(/Mon, 11 May/)).toBeDefined();
  });
});
