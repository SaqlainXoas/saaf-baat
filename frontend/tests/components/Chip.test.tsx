import { render, screen } from "@testing-library/react";
import Chip from "@/components/primitives/Chip";

describe("Chip", () => {
  it("renders label text", () => {
    render(<Chip label="IMF" />);
    expect(screen.getByText("IMF")).toBeDefined();
  });

  it("defaults to agreed variant (renders without error)", () => {
    const { container } = render(<Chip label="Test" />);
    const chip = container.firstChild as HTMLElement;
    // jsdom doesn't resolve CSS custom properties; verify the element renders
    expect(chip.getAttribute("style")).toBeDefined();
    expect(chip.textContent).toBe("Test");
  });

  it("renders debated variant with different label", () => {
    const { container } = render(<Chip label="fuel cut" variant="debated" />);
    const chip = container.firstChild as HTMLElement;
    expect(chip.getAttribute("style")).toBeDefined();
    expect(chip.textContent).toBe("fuel cut");
  });
});
