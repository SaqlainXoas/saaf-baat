import { render, screen } from "@testing-library/react";
import Pill, { getPillText } from "@/components/primitives/Pill";

describe("getPillText", () => {
  const cases: [string, string][] = [
    ["💳 WALLET", "WALLET"],
    ["🚦 COMMUTE", "COMMUTE"],
    ["🛡️ SAFETY", "SAFETY"],
    ["🏢 WORK", "WORK"],
    ["⚡ UTILITIES", "UTILITIES"],
    ["🏛️ GOVERNANCE", "GOVERNANCE"],
    ["", "UPDATE"],
    ["random", "UPDATE"],
  ];

  it.each(cases)('maps "%s" → "%s"', (input, expected) => {
    expect(getPillText(input)).toBe(expected);
  });
});

describe("Pill", () => {
  it("renders the extracted label text", () => {
    render(<Pill label="💳 WALLET" />);
    expect(screen.getByText("WALLET")).toBeDefined();
  });

  it("falls back to UPDATE for unknown input", () => {
    render(<Pill label="UNKNOWN" />);
    expect(screen.getByText("UPDATE")).toBeDefined();
  });

  it("renders the brand micro-icon span", () => {
    const { container } = render(<Pill label="🛡️ SAFETY" />);
    // The micro-icon is a child span with gradient background
    const spans = container.querySelectorAll("span");
    expect(spans.length).toBeGreaterThanOrEqual(2);
  });
});
