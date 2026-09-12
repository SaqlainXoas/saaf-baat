import { render, screen, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import BrandHeader from "@/components/BrandHeader";
import ThemeProvider from "@/components/ThemeProvider";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  useSearchParams: () => new URLSearchParams(""),
}));

describe("BrandHeader", () => {
  function renderHeader(props?: ComponentProps<typeof BrandHeader>) {
    return render(
      <ThemeProvider defaultTheme="system">
        <BrandHeader {...props} />
      </ThemeProvider>,
    );
  }

  afterEach(() => {
    jest.useRealTimers();
  });

  it("renders brand name and inline logo", () => {
    const { container } = renderHeader();
    expect(screen.getByText("Saaf Baat")).toBeDefined();
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("keeps a single appearance control and no Focus button", () => {
    renderHeader();
    expect(screen.queryByText("Focus")).toBeNull();
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("leads with the greeting, same as mobile", () => {
    renderHeader({ storyCount: 8 });
    const heading = screen.getByRole("heading", { level: 1 });

    // Same three bands as the mobile masthead, from the same component - the
    // desktop header is a server component and cannot resolve the hour itself.
    expect(within(heading).getByTitle("Good morning").textContent).toBe("Subah Bakhair");
    expect(heading.querySelectorAll("[data-band]")).toHaveLength(3);
  });

  it("uses Pakistan time for the edition date and singular story copy", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-04-07T20:30:00Z"));
    renderHeader({ storyCount: 1 });

    expect(screen.getByText(/Apr 8, 2026/)).toBeDefined();
    expect(screen.getByText(/1 essential story/)).toBeDefined();
  });

  it("says the story count exactly once", () => {
    // It used to appear three times: in the kicker, in a status pill and in
    // the ranking note, alongside the date twice.
    renderHeader({ storyCount: 9 });
    expect(screen.getAllByText(/9 essential stories/).length).toBe(1);
  });

  it("switches to latest-brief language for stale briefs", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-05-12T08:00:00Z"));
    renderHeader({ storyCount: 6, generatedAt: "2026-05-11T21:00:00Z", isFresh: false });

    expect(screen.getByText(/Latest brief/)).toBeDefined();
    expect(screen.queryByText(/Today's brief/)).toBeNull();
  });
});
