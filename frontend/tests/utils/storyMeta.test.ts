import {
  capitalise,
  formatCategory,
  formatRelativeTime,
  formatSourceDate,
  formatSourceTimestamp,
  getMetadataString,
} from "@/utils/storyMeta";

describe("storyMeta", () => {
  afterEach(() => jest.useRealTimers());

  it("capitalises without touching the rest of the word", () => {
    expect(capitalise("dawn")).toBe("Dawn");
    expect(capitalise("brecorder")).toBe("Brecorder");
    expect(capitalise("")).toBe("");
  });

  it("formats snake, kebab and spaced categories alike", () => {
    expect(formatCategory("economy")).toBe("Economy");
    expect(formatCategory("law_and_order")).toBe("Law And Order");
    expect(formatCategory("law-and-order")).toBe("Law And Order");
  });

  describe("getMetadataString", () => {
    it("returns the trimmed value", () => {
      expect(getMetadataString({ why_it_matters: "  Prices rise.  " }, "why_it_matters")).toBe(
        "Prices rise.",
      );
    });

    it("treats blank and missing alike, so a card omits rather than renders an empty line", () => {
      expect(getMetadataString({ why_it_matters: "   " }, "why_it_matters")).toBeNull();
      expect(getMetadataString({}, "why_it_matters")).toBeNull();
      expect(getMetadataString(undefined, "why_it_matters")).toBeNull();
    });

    it("refuses a non-string, rather than rendering '[object Object]'", () => {
      const metadata = { why_it_matters: { text: "nope" } } as never;
      expect(getMetadataString(metadata, "why_it_matters")).toBeNull();
    });
  });

  describe("formatRelativeTime", () => {
    beforeEach(() => {
      jest.useFakeTimers().setSystemTime(new Date("2026-08-25T12:00:00Z"));
    });

    it("steps through minutes, hours and days", () => {
      expect(formatRelativeTime("2026-08-25T11:59:40Z")).toBe("Just now");
      expect(formatRelativeTime("2026-08-25T11:30:00Z")).toBe("30m ago");
      expect(formatRelativeTime("2026-08-25T09:00:00Z")).toBe("3h ago");
      expect(formatRelativeTime("2026-08-23T12:00:00Z")).toBe("2d ago");
    });

    it("falls back to a date beyond a week", () => {
      expect(formatRelativeTime("2026-08-01T12:00:00Z")).toMatch(/Aug/);
    });

    it("never renders a negative age for a clock-skewed timestamp", () => {
      expect(formatRelativeTime("2026-08-25T13:00:00Z")).toBe("Just now");
    });

    it("returns null rather than 'Invalid Date' for junk", () => {
      expect(formatRelativeTime(undefined)).toBeNull();
      expect(formatRelativeTime("not a date")).toBeNull();
    });
  });

  it("renders source timestamps in Pakistan time", () => {
    // 04:30 UTC is 09:30 PKT. Rendering the UTC hour would tell a reader in
    // Karachi the story broke five hours before it did.
    expect(formatSourceTimestamp("2026-08-25T04:30:00Z")).toContain("9:30");
    expect(formatSourceTimestamp("2026-08-25T04:30:00Z")).toContain("PKT");
    expect(formatSourceTimestamp("nonsense")).toBeNull();
  });

  it("renders a date-only source without inventing a time", () => {
    const formatted = formatSourceDate("2026-08-25");
    expect(formatted).toMatch(/Aug/);
    expect(formatted).not.toMatch(/PKT|:/);
    expect(formatSourceDate(undefined)).toBeNull();
  });
});
