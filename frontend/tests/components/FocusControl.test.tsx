import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import FocusControl from "@/components/FocusControl";

const push = jest.fn();
const replace = jest.fn();
let queryString = "";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace }),
  useSearchParams: () => new URLSearchParams(queryString),
}));

describe("FocusControl", () => {
  beforeEach(() => {
    queryString = "";
    push.mockClear();
    replace.mockClear();
    window.localStorage.clear();
  });

  it("applies selected filters to the URL", () => {
    render(<FocusControl availableSources={["dawn", "geo"]} />);

    fireEvent.click(screen.getByText("Focus"));
    expect(screen.getByText("Impact")).toBeDefined();
    expect(screen.getByText("Sources")).toBeDefined();

    fireEvent.click(screen.getByText("WALLET"));
    fireEvent.click(screen.getByText("Dawn"));

    fireEvent.click(screen.getByText("Apply"));
    expect(push).toHaveBeenCalledWith("/?impact=WALLET&sources=dawn");
  });

  it("restores saved filters when URL has none", async () => {
    window.localStorage.setItem(
      "saaf-baat-focus",
      JSON.stringify({ impact: "WALLET", sources: "dawn" }),
    );

    render(<FocusControl availableSources={["dawn", "geo"]} />);
    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/?impact=WALLET&sources=dawn");
    });
  });

  it("prefers URL filters over localStorage values", async () => {
    queryString = "impact=SAFETY";
    window.localStorage.setItem(
      "saaf-baat-focus",
      JSON.stringify({ impact: "WALLET", sources: "dawn" }),
    );

    render(<FocusControl availableSources={["dawn", "geo"]} />);
    await waitFor(() => {
      expect(window.localStorage.getItem("saaf-baat-focus")).toContain("SAFETY");
    });
    expect(replace).not.toHaveBeenCalled();
  });

  it("clears quick focus and removes persisted filters", () => {
    queryString = "impact=WALLET&sources=dawn";
    window.localStorage.setItem(
      "saaf-baat-focus",
      JSON.stringify({ impact: "WALLET", sources: "dawn" }),
    );

    render(<FocusControl availableSources={["dawn", "geo"]} />);
    fireEvent.click(screen.getByText("Clear focus"));

    expect(push).toHaveBeenCalledWith("/");
    expect(window.localStorage.getItem("saaf-baat-focus")).toBeNull();
  });
});
