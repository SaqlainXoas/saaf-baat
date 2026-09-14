import { render, screen } from "@testing-library/react";
import DataStatusBanner from "@/components/DataStatusBanner";

describe("DataStatusBanner", () => {
  it("renders nothing when live feed is fresh", () => {
    const fresh = new Date(Date.now() - 30 * 60 * 1000).toISOString();
    const { container } = render(<DataStatusBanner status="live" generatedAt={fresh} isFresh storyCount={7} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows stale warning when live feed is old", () => {
    const stale = new Date(Date.now() - 8 * 60 * 60 * 1000).toISOString();
    render(<DataStatusBanner status="live" generatedAt={stale} isFresh={false} storyCount={7} />);
    expect(screen.getByRole("status").textContent).toContain("Brief not updated yet today");
  });

  it("says nothing about a short brief, which is the product working", () => {
    // This used to raise "Partial brief — ... We haven't added filler." in the
    // same amber box as a dead backend. The brief is finite on purpose, the
    // masthead already states the count, and warning a reader that a finite
    // product is finite argues against it.
    const { container } = render(
      <DataStatusBanner status="live" generatedAt={new Date().toISOString()} isFresh storyCount={5} />,
    );
    expect(screen.queryByRole("status")).toBeNull();
    expect(container.innerHTML).toBe("");
  });

  it("still warns about the faults that are faults", () => {
    render(<DataStatusBanner status="live" isFresh={false} storyCount={0} />);
    expect(screen.getByRole("status").textContent).toContain("being prepared");
  });

  it("shows the empty-state preparation message for a zero-story live feed", () => {
    render(<DataStatusBanner status="live" isFresh={false} storyCount={0} />);
    expect(screen.getByRole("status").textContent).toContain("The morning brief is being prepared");
  });

  it("announces status changes politely to assistive tech", () => {
    render(<DataStatusBanner status="mock-no-api" />);
    expect(screen.getByRole("status").getAttribute("aria-live")).toBe("polite");
  });

  it("shows strict live mode error message", () => {
    render(
      <DataStatusBanner
        status="error-live-required"
        message="Unable to load brief. Please try again shortly. (HTTP 503)"
      />,
    );
    expect(screen.getByRole("status").textContent).toContain("HTTP 503");
  });

  it("does not invent a last successful update when no live timestamp exists", () => {
    render(<DataStatusBanner status="mock-no-api" />);
    expect(screen.getByRole("status").textContent).not.toContain("Last successful live update");
  });
});

 it("prioritises stale edition warning over short edition copy", () => {
   render(<DataStatusBanner status="live" isFresh={false} storyCount={4} />);
   expect(screen.getByRole("status")).toHaveTextContent("older edition");
   expect(screen.getByRole("status")).not.toHaveTextContent("being reviewed");
 });
