import { IMPACT_LABELS, normaliseImpact } from "@/utils/impact";

describe("normaliseImpact", () => {
  it("strips the emoji the backend ships with each label", () => {
    expect(normaliseImpact("💳 WALLET")).toBe("WALLET");
    expect(normaliseImpact("🚌 COMMUTE")).toBe("COMMUTE");
    expect(normaliseImpact("🏛️ GOVERNANCE")).toBe("GOVERNANCE");
  });

  it("accepts a bare label in any case", () => {
    expect(normaliseImpact("safety")).toBe("SAFETY");
    expect(normaliseImpact("  Work  ")).toBe("WORK");
  });

  it("falls back to UPDATE rather than rendering an unknown label", () => {
    expect(normaliseImpact("")).toBe("UPDATE");
    expect(normaliseImpact("🐈 CATS")).toBe("UPDATE");
  });

  it("round-trips every label the product defines", () => {
    IMPACT_LABELS.forEach((label) => expect(normaliseImpact(label)).toBe(label));
  });
});
