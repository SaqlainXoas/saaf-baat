import { fireEvent, render, screen } from "@testing-library/react";
import SkipLink from "@/components/SkipLink";

describe("SkipLink", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  function mountTarget(attrs = "") {
    document.body.insertAdjacentHTML("beforeend", `<div data-skip-target="stories" ${attrs}>lead</div>`);
    return document.querySelector<HTMLElement>('[data-skip-target="stories"]')!;
  }

  it("moves focus to the target instead of navigating to '#'", () => {
    const target = mountTarget();
    render(<SkipLink label="Skip to stories" selector='[data-skip-target="stories"]' />);

    fireEvent.click(screen.getByText("Skip to stories"));
    expect(document.activeElement).toBe(target);
  });

  it("makes a non-focusable target focusable rather than silently doing nothing", () => {
    const target = mountTarget();
    expect(target.hasAttribute("tabindex")).toBe(false);

    render(<SkipLink label="Skip to stories" selector='[data-skip-target="stories"]' />);
    fireEvent.click(screen.getByText("Skip to stories"));

    expect(target.getAttribute("tabindex")).toBe("-1");
  });

  it("leaves an existing tabindex alone", () => {
    const target = mountTarget('tabindex="0"');
    render(<SkipLink label="Skip to stories" selector='[data-skip-target="stories"]' />);
    fireEvent.click(screen.getByText("Skip to stories"));
    expect(target.getAttribute("tabindex")).toBe("0");
  });

  it("does not throw when the target is not on the page", () => {
    // Both layouts render the link unconditionally, including on the empty
    // and error states where there is no lead story to skip to.
    render(<SkipLink label="Skip to stories" selector='[data-skip-target="missing"]' />);
    expect(() => fireEvent.click(screen.getByText("Skip to stories"))).not.toThrow();
  });

  it("stays keyboard-reachable", () => {
    render(<SkipLink label="Skip to stories" selector='[data-skip-target="stories"]' />);
    expect(screen.getByText("Skip to stories").className).toContain("sb-focusable");
  });
});
