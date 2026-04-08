import { render, screen } from "@testing-library/react";
import MorningGreeting from "@/components/MorningGreeting";

describe("MorningGreeting", () => {
  it("renders the city name", () => {
    render(<MorningGreeting storyCount={5} />);
    expect(screen.getAllByText(/Islamabad/).length).toBeGreaterThan(0);
  });

  it("shows story count in context line", () => {
    render(<MorningGreeting storyCount={7} />);
    expect(screen.getByText(/7 essential stories/)).toBeDefined();
  });

  it("renders the greeting phrase", () => {
    render(<MorningGreeting storyCount={3} />);
    const el = screen.getByText(/Subah Bakhair/);
    expect(el).toBeDefined();
  });

  it("does not render fake weather", () => {
    render(<MorningGreeting storyCount={5} />);
    expect(screen.queryByText(/°C/)).toBeNull();
  });

  it("guides the user to start with the lead story", () => {
    render(<MorningGreeting storyCount={5} />);
    expect(screen.getByText(/Start with the lead story/i)).toBeDefined();
  });

  it("renders a real edition date instead of a placeholder label", () => {
    render(<MorningGreeting storyCount={5} />);
    expect(screen.queryByText(/^Today$/)).toBeNull();
    expect(screen.getByText(/^[A-Z][a-z]{2}, \d{1,2} [A-Z][a-z]{2}$/)).toBeDefined();
  });
});
