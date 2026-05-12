import { render, screen } from "@testing-library/react";
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

  it("renders brand name", () => {
    renderHeader();
    expect(screen.getByText("Saaf Baat")).toBeDefined();
  });

  it("renders inline logo", () => {
    const { container } = renderHeader();
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("renders Focus button", () => {
    renderHeader();
    expect(screen.getByText("Focus")).toBeDefined();
  });

  it("uses Pakistan time for the edition date and singular story copy", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-04-07T20:30:00Z"));
    renderHeader({ storyCount: 1 });

    expect(screen.getByText("Apr 8, 2026")).toBeDefined();
    expect(screen.getByText("Today's Brief · Wednesday, April 8")).toBeDefined();
    expect(screen.getAllByText("1 essential story").length).toBeGreaterThan(0);
  });
});
