import { render, screen } from "@testing-library/react";
import DataStatusBanner from "@/components/DataStatusBanner";

describe("DataStatusBanner", () => {
  it("renders nothing when live feed is fresh", () => {
    const fresh = new Date(Date.now() - 30 * 60 * 1000).toISOString();
    const { container } = render(<DataStatusBanner status="live" latestCreatedAt={fresh} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows stale warning when live feed is old", () => {
    const stale = new Date(Date.now() - 8 * 60 * 60 * 1000).toISOString();
    render(<DataStatusBanner status="live" latestCreatedAt={stale} />);
    expect(screen.getByRole("status").textContent).toContain("This brief may be stale");
  });

  it("announces status changes politely to assistive tech", () => {
    render(<DataStatusBanner status="mock-no-api" />);
    expect(screen.getByRole("status").getAttribute("aria-live")).toBe("polite");
  });

  it("shows strict live mode error message", () => {
    render(
      <DataStatusBanner
        status="error-live-required"
        message="Live feed request failed with HTTP 503."
      />,
    );
    expect(screen.getByRole("status").textContent).toContain("HTTP 503");
  });

  it("does not invent a last successful update when no live timestamp exists", () => {
    render(<DataStatusBanner status="mock-no-api" />);
    expect(screen.getByRole("status").textContent).not.toContain("Last successful live update");
  });
});
