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
    expect(screen.getByRole("status").textContent).toContain("Feed may be stale");
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
});
