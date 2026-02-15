import { render, screen } from "@testing-library/react";
import ConsensusEngine from "@/components/ConsensusEngine";

const facts = [
  { text: "IMF confirms tranche release", type: "ORG", sources: 3 },
  { text: "SBP reserves increase", type: "ORG", sources: 3 },
  { text: "Extra fact that should be cut", type: "ORG", sources: 2 },
];

const claims = [
  { text: "Long-term inflation impact", type: "MISC", sources: 2 },
  { text: "Second claim that should be cut", type: "MISC", sources: 1 },
];

describe("ConsensusEngine", () => {
  it("renders section heading", () => {
    render(<ConsensusEngine confirmedFacts={facts} debatedClaims={claims} sourceCount={3} />);
    expect(screen.getByText("Consensus Engine")).toBeDefined();
  });

  it("renders What's agreed block", () => {
    render(<ConsensusEngine confirmedFacts={facts} debatedClaims={claims} sourceCount={3} />);
    expect(screen.getByText("What's agreed")).toBeDefined();
  });

  it("renders What's debated block", () => {
    render(<ConsensusEngine confirmedFacts={facts} debatedClaims={claims} sourceCount={3} />);
    expect(screen.getByText("What's debated")).toBeDefined();
  });

  it("caps agreed facts at 2", () => {
    render(<ConsensusEngine confirmedFacts={facts} debatedClaims={claims} sourceCount={3} />);
    expect(screen.getByText("IMF confirms tranche release")).toBeDefined();
    expect(screen.getByText("SBP reserves increase")).toBeDefined();
    expect(screen.queryByText("Extra fact that should be cut")).toBeNull();
  });

  it("caps debated claims at 1", () => {
    render(<ConsensusEngine confirmedFacts={facts} debatedClaims={claims} sourceCount={3} />);
    expect(screen.getByText("Long-term inflation impact")).toBeDefined();
    expect(screen.queryByText("Second claim that should be cut")).toBeNull();
  });

  it("shows source count", () => {
    render(<ConsensusEngine confirmedFacts={[]} debatedClaims={[]} sourceCount={5} />);
    expect(screen.getByText(/assessed: 5/)).toBeDefined();
  });

  it("renders empty-state copy when consensus lists are empty", () => {
    render(<ConsensusEngine confirmedFacts={[]} debatedClaims={[]} sourceCount={1} />);
    expect(screen.getByText("No clear consensus yet.")).toBeDefined();
    expect(screen.getByText("No major debated claims.")).toBeDefined();
  });

  it("renders checkmark icons for agreed items", () => {
    render(<ConsensusEngine confirmedFacts={facts.slice(0, 1)} debatedClaims={[]} sourceCount={1} />);
    expect(screen.getByText("✓")).toBeDefined();
  });

  it("renders question-mark icons for debated items", () => {
    render(<ConsensusEngine confirmedFacts={[]} debatedClaims={claims.slice(0, 1)} sourceCount={1} />);
    expect(screen.getByText("?")).toBeDefined();
  });
});
