import { render, screen } from "@testing-library/react";
import Logo from "@/components/Logo";

describe("Logo", () => {
  it("is announced when it stands for the brand", () => {
    render(<Logo />);
    expect(screen.getByRole("img", { name: "Saaf Baat logo" })).toBeDefined();
  });

  it("is hidden from assistive tech when it sits next to the wordmark", () => {
    // Both mastheads render the mark beside the words "Saaf Baat"; announcing
    // it too would read the brand name twice.
    const { container } = render(<Logo decorative />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("aria-hidden")).toBe("true");
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("honours the requested size", () => {
    const { container } = render(<Logo size={40} decorative />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("width")).toBe("40");
    expect(svg?.getAttribute("height")).toBe("40");
  });
});
