import { render, screen } from "@testing-library/react";
import MorningGreeting from "@/components/MorningGreeting";

describe("MorningGreeting", () => {
  it("renders the city name", () => {
    render(<MorningGreeting storyCount={5} />);
    expect(screen.getByText(/Islamabad/)).toBeDefined();
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
});
