import { render, screen, within } from "@testing-library/react";
import MastheadGreeting from "@/components/MastheadGreeting";
import { GREETING_BANDS } from "@/utils/edition";

describe("MastheadGreeting", () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  it("renders every time band, so CSS can pick one without React re-rendering", () => {
    render(<MastheadGreeting className="sb-display-home" />);
    const heading = screen.getByRole("heading", { level: 1 });

    for (const { band, greeting, translation } of GREETING_BANDS) {
      const span = heading.querySelector(`[data-band="${band}"]`);
      expect(span).not.toBeNull();
      expect(span?.textContent).toBe(greeting);
      expect(span?.getAttribute("title")).toBe(translation);
    }
    expect(heading.querySelectorAll("[data-band]")).toHaveLength(3);
  });

  it("carries the three bands the product was specified with", () => {
    render(<MastheadGreeting className="sb-display-home" />);
    const heading = screen.getByRole("heading", { level: 1 });

    expect(within(heading).getByTitle("Good morning").textContent).toBe("Subah Bakhair");
    expect(within(heading).getByTitle("Today's word").textContent).toBe("Aaj Ki Baat");
    expect(within(heading).getByTitle("Good evening").textContent).toBe("Shaam Bakhair");
  });

  it("marks the heading as romanised Urdu and takes its size from the caller", () => {
    render(<MastheadGreeting className="sb-display-mobile" />);
    const heading = screen.getByRole("heading", { level: 1 });

    expect(heading.getAttribute("lang")).toBe("ur-Latn");
    expect(heading.className).toBe("sb-display-mobile");
  });

  it("renders identical markup whatever the clock says", () => {
    // Band selection is CSS-side, off data-pkt-band. If React output ever
    // varied by the hour, a page rendered at 06:00 and served from Vercel's
    // cache at 20:00 would be wrong, and hydration would mismatch.
    jest.useFakeTimers().setSystemTime(new Date("2026-09-12T01:00:00Z")); // 06:00 PKT
    const morning = render(<MastheadGreeting className="sb-display-home" />).container.innerHTML;

    jest.setSystemTime(new Date("2026-09-12T16:00:00Z")); // 21:00 PKT
    const evening = render(<MastheadGreeting className="sb-display-home" />).container.innerHTML;

    expect(evening).toBe(morning);
  });
});
