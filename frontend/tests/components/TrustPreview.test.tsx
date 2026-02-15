import { render, screen } from "@testing-library/react";
import TrustPreview from "@/components/TrustPreview";

const facts = [
  { text: "IMF", type: "ORG", sources: 3 },
  { text: "Pakistan", type: "GPE", sources: 3 },
  { text: "SBP", type: "ORG", sources: 2 }, // third — should be cut
];

const claims = [
  { text: "fuel cut", type: "MISC", sources: 2 },
  { text: "bonus claim", type: "MISC", sources: 1 }, // second — should be cut
];

describe("TrustPreview", () => {
  it("renders section labels", () => {
    render(<TrustPreview confirmedFacts={[]} debatedClaims={[]} />);
    expect(screen.getByText("Agreed across sources")).toBeDefined();
    expect(screen.getByText("Debated / emerging")).toBeDefined();
  });

  it("shows max 2 agreed chips", () => {
    render(<TrustPreview confirmedFacts={facts} debatedClaims={claims} />);
    expect(screen.getByText("IMF")).toBeDefined();
    expect(screen.getByText("Pakistan")).toBeDefined();
    expect(screen.queryByText("SBP")).toBeNull();
  });

  it("shows max 1 debated chip", () => {
    render(<TrustPreview confirmedFacts={facts} debatedClaims={claims} />);
    expect(screen.getByText("fuel cut")).toBeDefined();
    expect(screen.queryByText("bonus claim")).toBeNull();
  });
});
